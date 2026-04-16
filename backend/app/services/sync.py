"""Mobile Sync service — device registration, pull, push operations."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.infra.models import (
    Account,
    BankTransaction,
    Bill,
    Contact,
    ExpenseClaim,
    Invoice,
    Item,
    JournalEntry,
    Payment,
    Period,
    SyncDevice,
    SyncOp,
)

log = get_logger(__name__)


class SyncDeviceNotFoundError(ValueError):
    pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _serialize(value: object) -> object:
    """Convert Decimal and datetime values to JSON-safe scalars."""
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _row_to_dict(obj: object) -> dict:
    """Serialize an ORM row to a plain dict, converting money/datetime fields."""
    result: dict = {}
    for col in obj.__table__.columns:  # type: ignore[attr-defined]
        val = getattr(obj, col.name)
        result[col.name] = _serialize(val)
    return result


# ---------------------------------------------------------------------------
# Device management
# ---------------------------------------------------------------------------


async def register_device(
    db: AsyncSession,
    tenant_id: str,
    user_id: str,
    *,
    platform: str,
    app_version: str | None,
    device_fingerprint: str,
    push_token: str | None = None,
) -> SyncDevice:
    """Upsert device registration — update push_token + last_seen if fingerprint exists."""
    now = datetime.now(tz=UTC)
    device = await db.scalar(
        select(SyncDevice).where(
            SyncDevice.tenant_id == tenant_id,
            SyncDevice.device_fingerprint == device_fingerprint,
        )
    )
    if device:
        device.push_token = push_token
        device.last_seen = now
        device.updated_at = now
        if app_version is not None:
            device.app_version = app_version
    else:
        device = SyncDevice(
            tenant_id=tenant_id,
            user_id=user_id,
            device_fingerprint=device_fingerprint,
            platform=platform,
            app_version=app_version,
            push_token=push_token,
            last_seen=now,
        )
        db.add(device)

    await db.flush()
    await db.refresh(device)
    log.info("sync.device.registered", tenant_id=tenant_id, fingerprint=device_fingerprint)
    return device


async def update_push_token(
    db: AsyncSession,
    tenant_id: str,
    device_fingerprint: str,
    push_token: str,
) -> SyncDevice:
    """Update the push notification token for a registered device."""
    device = await db.scalar(
        select(SyncDevice).where(
            SyncDevice.tenant_id == tenant_id,
            SyncDevice.device_fingerprint == device_fingerprint,
        )
    )
    if not device:
        raise SyncDeviceNotFoundError(device_fingerprint)

    now = datetime.now(tz=UTC)
    device.push_token = push_token
    device.last_seen = now
    device.updated_at = now

    await db.flush()
    await db.refresh(device)
    log.info("sync.device.push_token_updated", tenant_id=tenant_id, fingerprint=device_fingerprint)
    return device


# ---------------------------------------------------------------------------
# Pull
# ---------------------------------------------------------------------------

_JOURNAL_PULL_DAYS = 90


async def pull_changes(
    db: AsyncSession,
    tenant_id: str,
    *,
    cursor: str | None,
    limit: int = 100,
) -> dict:
    """
    Return entities changed since cursor (ISO timestamp).

    cursor format: ISO-8601 timestamp string (updated_at > cursor).
    Returns:
      {
        accounts, periods, contacts, items, invoices, bills, payments,
        journal_entries,   # posted only, last 90 days
        next_cursor        # new ISO timestamp (now)
      }
    Each entity is a dict with all scalar fields serialized (Decimal → str, datetime → isoformat).
    """
    now = datetime.now(tz=UTC)
    since: datetime | None = None
    if cursor:
        try:
            since = datetime.fromisoformat(cursor)
        except ValueError:
            since = None

    def _apply_cursor(q: object, model: object) -> object:  # type: ignore[type-arg]
        if since is not None:
            q = q.where(model.updated_at > since)  # type: ignore[union-attr]
        return q.limit(limit)  # type: ignore[union-attr]

    # accounts
    accounts_q = _apply_cursor(
        select(Account).where(Account.tenant_id == tenant_id).order_by(Account.updated_at),
        Account,
    )
    accounts = [_row_to_dict(r) for r in (await db.execute(accounts_q)).scalars()]

    # periods
    periods_q = _apply_cursor(
        select(Period).where(Period.tenant_id == tenant_id).order_by(Period.updated_at),
        Period,
    )
    periods = [_row_to_dict(r) for r in (await db.execute(periods_q)).scalars()]

    # contacts
    contacts_q = _apply_cursor(
        select(Contact).where(Contact.tenant_id == tenant_id).order_by(Contact.updated_at),
        Contact,
    )
    contacts = [_row_to_dict(r) for r in (await db.execute(contacts_q)).scalars()]

    # items
    items_q = _apply_cursor(
        select(Item).where(Item.tenant_id == tenant_id).order_by(Item.updated_at),
        Item,
    )
    items = [_row_to_dict(r) for r in (await db.execute(items_q)).scalars()]

    # invoices
    invoices_q = _apply_cursor(
        select(Invoice).where(Invoice.tenant_id == tenant_id).order_by(Invoice.updated_at),
        Invoice,
    )
    invoices = [_row_to_dict(r) for r in (await db.execute(invoices_q)).scalars()]

    # bills
    bills_q = _apply_cursor(
        select(Bill).where(Bill.tenant_id == tenant_id).order_by(Bill.updated_at),
        Bill,
    )
    bills = [_row_to_dict(r) for r in (await db.execute(bills_q)).scalars()]

    # payments
    payments_q = _apply_cursor(
        select(Payment).where(Payment.tenant_id == tenant_id).order_by(Payment.updated_at),
        Payment,
    )
    payments = [_row_to_dict(r) for r in (await db.execute(payments_q)).scalars()]

    # journal_entries — posted only, last 90 days
    from datetime import timedelta

    cutoff = now - timedelta(days=_JOURNAL_PULL_DAYS)
    je_q = (
        select(JournalEntry)
        .where(
            JournalEntry.tenant_id == tenant_id,
            JournalEntry.status == "posted",
            JournalEntry.posted_at >= cutoff,
        )
        .order_by(JournalEntry.updated_at)
    )
    if since is not None:
        je_q = je_q.where(JournalEntry.updated_at > since)
    je_q = je_q.limit(limit)
    journal_entries = [_row_to_dict(r) for r in (await db.execute(je_q)).scalars()]

    return {
        "accounts": accounts,
        "periods": periods,
        "contacts": contacts,
        "items": items,
        "invoices": invoices,
        "bills": bills,
        "payments": payments,
        "journal_entries": journal_entries,
        "next_cursor": now.isoformat(),
    }


# ---------------------------------------------------------------------------
# Push
# ---------------------------------------------------------------------------

_SUPPORTED_ENTITY_TYPES = {"expense_claim", "bank_transaction"}


async def push_operations(
    db: AsyncSession,
    tenant_id: str,
    user_id: str,
    device_id: str | None,
    ops: list[dict],
) -> list[dict]:
    """
    Apply a batch of client mutations.

    Each op: {client_op_id, entity_type, entity_id, base_version, new_state}

    Supported entity_types:
      - 'expense_claim'    — create or update draft only
      - 'bank_transaction' — create only

    Returns list of {client_op_id, status, applied_version?, server_state?, error?}
    """
    now = datetime.now(tz=UTC)
    results: list[dict] = []

    for op in ops:
        client_op_id: str = op["client_op_id"]
        entity_type: str = op.get("entity_type", "")
        entity_id: str | None = op.get("entity_id")
        base_version: int | None = op.get("base_version")
        new_state: dict = op.get("new_state", {})

        # Idempotency: check if already processed
        existing = await db.scalar(select(SyncOp).where(SyncOp.client_op_id == client_op_id))
        if existing:
            result: dict = {"client_op_id": client_op_id, "status": existing.status}
            if existing.applied_version is not None:
                result["applied_version"] = existing.applied_version
            if existing.error:
                result["error"] = existing.error
            results.append(result)
            continue

        # Validate entity type
        if entity_type not in _SUPPORTED_ENTITY_TYPES:
            sync_op = SyncOp(
                tenant_id=tenant_id,
                client_op_id=client_op_id,
                device_id=device_id,
                entity_type=entity_type,
                entity_id=entity_id,
                base_version=base_version,
                status="error",
                error=f"Unsupported entity_type: {entity_type}",
                created_at=now,
            )
            db.add(sync_op)
            await db.flush()
            results.append(
                {
                    "client_op_id": client_op_id,
                    "status": "error",
                    "error": sync_op.error,
                }
            )
            continue

        # Dispatch by entity type
        try:
            if entity_type == "expense_claim":
                applied_version, server_state = await _apply_expense_claim_op(
                    db, tenant_id, user_id, entity_id, base_version, new_state, now
                )
            else:  # bank_transaction
                applied_version, server_state = await _apply_bank_transaction_op(
                    db, tenant_id, user_id, entity_id, new_state, now
                )
        except _ConflictError as exc:
            sync_op = SyncOp(
                tenant_id=tenant_id,
                client_op_id=client_op_id,
                device_id=device_id,
                entity_type=entity_type,
                entity_id=entity_id,
                base_version=base_version,
                status="conflict",
                error=str(exc),
                created_at=now,
            )
            db.add(sync_op)
            await db.flush()
            results.append(
                {
                    "client_op_id": client_op_id,
                    "status": "conflict",
                    "server_state": exc.server_state,
                }
            )
            continue
        except Exception as exc:
            sync_op = SyncOp(
                tenant_id=tenant_id,
                client_op_id=client_op_id,
                device_id=device_id,
                entity_type=entity_type,
                entity_id=entity_id,
                base_version=base_version,
                status="error",
                error=str(exc),
                created_at=now,
            )
            db.add(sync_op)
            await db.flush()
            results.append(
                {
                    "client_op_id": client_op_id,
                    "status": "error",
                    "error": str(exc),
                }
            )
            continue

        # Success
        sync_op = SyncOp(
            tenant_id=tenant_id,
            client_op_id=client_op_id,
            device_id=device_id,
            entity_type=entity_type,
            entity_id=entity_id,
            base_version=base_version,
            applied_version=applied_version,
            status="applied",
            applied_at=now,
            created_at=now,
        )
        db.add(sync_op)
        await db.flush()
        results.append(
            {
                "client_op_id": client_op_id,
                "status": "applied",
                "applied_version": applied_version,
                "server_state": server_state,
            }
        )

    return results


class _ConflictError(Exception):
    def __init__(self, msg: str, server_state: dict) -> None:
        super().__init__(msg)
        self.server_state = server_state


async def _apply_expense_claim_op(
    db: AsyncSession,
    tenant_id: str,
    user_id: str,
    entity_id: str | None,
    base_version: int | None,
    new_state: dict,
    now: datetime,
) -> tuple[int, dict]:
    """Create or update a draft expense claim. Returns (applied_version, server_state)."""
    if entity_id:
        # Update existing draft
        claim = await db.scalar(
            select(ExpenseClaim).where(
                ExpenseClaim.id == entity_id,
                ExpenseClaim.tenant_id == tenant_id,
            )
        )
        if not claim:
            raise ValueError(f"ExpenseClaim {entity_id} not found")

        if base_version is not None and claim.version != base_version:
            raise _ConflictError(
                f"Version mismatch: expected {base_version}, got {claim.version}",
                server_state=_row_to_dict(claim),
            )

        if claim.status != "draft":
            raise ValueError(f"Cannot update expense claim with status '{claim.status}' via sync")

        # Apply allowed fields from new_state
        for field in ("title", "description", "currency"):
            if field in new_state:
                setattr(claim, field, new_state[field])

        claim.updated_by = user_id
        claim.updated_at = now
        claim.version += 1
        await db.flush()
        await db.refresh(claim)
        return claim.version, _row_to_dict(claim)
    else:
        # Create new draft expense claim
        from sqlalchemy import func

        count_result = await db.execute(
            select(func.count())
            .select_from(ExpenseClaim)
            .where(ExpenseClaim.tenant_id == tenant_id)
        )
        seq = (count_result.scalar() or 0) + 1
        claim = ExpenseClaim(
            tenant_id=tenant_id,
            number=f"EXP-{seq:06d}",
            contact_id=new_state["contact_id"],
            status="draft",
            claim_date=new_state.get("claim_date", now.date()),
            title=new_state.get("title", ""),
            description=new_state.get("description"),
            currency=new_state.get("currency", "USD"),
            total_amount=Decimal(str(new_state.get("total_amount", "0"))),
            tax_total=Decimal(str(new_state.get("tax_total", "0"))),
            created_by=user_id,
            updated_by=user_id,
        )
        db.add(claim)
        await db.flush()
        await db.refresh(claim)
        return claim.version, _row_to_dict(claim)


async def _apply_bank_transaction_op(
    db: AsyncSession,
    tenant_id: str,
    user_id: str,
    entity_id: str | None,
    new_state: dict,
    now: datetime,
) -> tuple[int, dict]:
    """Create a bank transaction (create only via sync). Returns (applied_version, server_state)."""
    txn = BankTransaction(
        tenant_id=tenant_id,
        bank_account_id=new_state["bank_account_id"],
        transaction_date=new_state.get("transaction_date", now.date()),
        description=new_state.get("description"),
        reference=new_state.get("reference"),
        amount=Decimal(str(new_state["amount"])),
        currency=new_state.get("currency", "USD"),
        is_reconciled=False,
        created_by=user_id,
        updated_by=user_id,
    )
    db.add(txn)
    await db.flush()
    await db.refresh(txn)
    return txn.version, _row_to_dict(txn)
