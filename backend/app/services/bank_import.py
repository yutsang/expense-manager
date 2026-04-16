"""Bank statement CSV import — auto-detects format, creates BankTransaction rows."""
from __future__ import annotations

import contextlib
import csv
import io
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.infra.models import BankTransaction

log = get_logger(__name__)

_QUANTIZE_4 = Decimal("0.0001")

_DATE_FORMATS = [
    "%Y-%m-%d",
    "%d/%m/%Y",
    "%m/%d/%Y",
    "%d-%m-%Y",
    "%d %b %Y",
    "%d %B %Y",
]


def _parse_date(value: str) -> date:
    """Try each supported date format and return the first that parses."""
    value = value.strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Unrecognised date format: {value!r}")


def _normalise_header(headers: list[str]) -> list[str]:
    return [h.strip().lower() for h in headers]


def _detect_format(headers: list[str]) -> str:
    """Return 'split' if debit/credit columns exist, else 'single'."""
    normalised = _normalise_header(headers)
    if "debit" in normalised and "credit" in normalised:
        return "split"
    return "single"


def _parse_amount(value: str) -> Decimal:
    """Parse an amount string, stripping currency symbols and commas."""
    cleaned = value.strip().replace(",", "").replace("$", "").replace("£", "").replace("€", "")
    if not cleaned:
        return Decimal("0")
    return Decimal(cleaned)


async def import_csv(
    db: AsyncSession,
    *,
    tenant_id: str,
    actor_id: str | None,
    bank_account_id: str,
    csv_bytes: bytes,
    currency: str = "USD",
    skip_duplicates: bool = True,
) -> dict:
    """Parse CSV, create BankTransaction rows. Returns summary dict."""
    # Decode: try UTF-8 first, fall back to latin-1
    try:
        text = csv_bytes.decode("utf-8")
    except UnicodeDecodeError:
        text = csv_bytes.decode("latin-1")

    reader = csv.reader(io.StringIO(text))
    rows = list(reader)

    if not rows:
        return {"imported": 0, "skipped_duplicates": 0, "errors": ["Empty file"]}

    headers = rows[0]
    normalised = _normalise_header(headers)
    fmt = _detect_format(headers)

    # Map column positions
    try:
        date_col = normalised.index("date")
    except ValueError:
        return {"imported": 0, "skipped_duplicates": 0, "errors": ["CSV missing 'date' column"]}

    desc_col: int | None = None
    for candidate in ("description", "details", "memo", "narrative", "narration"):
        if candidate in normalised:
            desc_col = normalised.index(candidate)
            break

    if fmt == "split":
        try:
            debit_col = normalised.index("debit")
            credit_col = normalised.index("credit")
        except ValueError:
            return {"imported": 0, "skipped_duplicates": 0, "errors": ["CSV missing 'debit' or 'credit' column"]}
        amount_col = None
    else:
        amount_col_name = None
        for candidate in ("amount", "value", "transaction amount"):
            if candidate in normalised:
                amount_col_name = candidate
                break
        if amount_col_name is None:
            return {"imported": 0, "skipped_duplicates": 0, "errors": ["CSV missing 'amount' column"]}
        amount_col = normalised.index(amount_col_name)
        debit_col = None
        credit_col = None

    # Load existing transactions for duplicate detection
    existing_keys: set[tuple[str, str, str, str]] = set()
    if skip_duplicates:
        q = select(
            BankTransaction.transaction_date,
            BankTransaction.amount,
            BankTransaction.description,
        ).where(
            BankTransaction.tenant_id == tenant_id,
            BankTransaction.bank_account_id == bank_account_id,
        )
        result = await db.execute(q)
        for row_db in result:
            tx_date = str(row_db[0])
            tx_amount = str(row_db[1])
            tx_desc = (row_db[2] or "")[:50]
            existing_keys.add((bank_account_id, tx_date, tx_amount, tx_desc))

    imported = 0
    skipped_duplicates = 0
    errors: list[str] = []

    for row_no, row in enumerate(rows[1:], start=2):
        if not any(cell.strip() for cell in row):
            continue  # skip blank rows

        try:
            raw_date = row[date_col]
            parsed_date = _parse_date(raw_date)
        except (ValueError, IndexError) as exc:
            errors.append(f"Row {row_no}: {exc}")
            continue

        description = ""
        if desc_col is not None:
            with contextlib.suppress(IndexError):
                description = row[desc_col].strip()

        try:
            if fmt == "split":
                raw_debit = row[debit_col] if debit_col is not None and debit_col < len(row) else ""  # type: ignore[index]
                raw_credit = row[credit_col] if credit_col is not None and credit_col < len(row) else ""  # type: ignore[index]
                debit_amt = _parse_amount(raw_debit)
                credit_amt = _parse_amount(raw_credit)
                # debit = money out (negative), credit = money in (positive)
                amount = (credit_amt - debit_amt).quantize(_QUANTIZE_4)
            else:
                raw_amount = row[amount_col] if amount_col is not None and amount_col < len(row) else ""  # type: ignore[index]
                amount = _parse_amount(raw_amount).quantize(_QUANTIZE_4)
        except (InvalidOperation, IndexError) as exc:
            errors.append(f"Row {row_no}: invalid amount — {exc}")
            continue

        if skip_duplicates:
            key = (bank_account_id, str(parsed_date), str(amount), description[:50])
            if key in existing_keys:
                skipped_duplicates += 1
                continue

        txn = BankTransaction(
            tenant_id=tenant_id,
            bank_account_id=bank_account_id,
            transaction_date=parsed_date,
            description=description or None,
            amount=amount,
            currency=currency,
            is_reconciled=False,
            created_by=actor_id,
            updated_by=actor_id,
        )
        db.add(txn)
        imported += 1

        if skip_duplicates:
            existing_keys.add((bank_account_id, str(parsed_date), str(amount), description[:50]))

    await db.flush()
    log.info(
        "bank_import.complete",
        tenant_id=tenant_id,
        bank_account_id=bank_account_id,
        imported=imported,
        skipped=skipped_duplicates,
        errors=len(errors),
    )
    return {"imported": imported, "skipped_duplicates": skipped_duplicates, "errors": errors}
