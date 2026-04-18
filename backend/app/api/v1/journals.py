"""Journals API — create draft, post, void, list, get."""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, Query, Response, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from app.api.v1.deps import ActorId, DbSession, TenantId
from app.api.v1.schemas import (
    ApproveRejectRequest,
    CsvImportResult,
    JournalCreate,
    JournalListResponse,
    JournalResponse,
    JournalVoidRequest,
    ProblemDetail,
)
from app.domain.ledger.journal import JournalBalanceError, JournalLineInput, JournalStatusError
from app.infra.models import Account, JournalLine
from app.services.csv_import import generate_template_csv, parse_csv, parse_date, parse_decimal
from app.services.journals import (
    ControlAccountError,
    FutureDateError,
    InvalidAccountError,
    JournalNotFoundError,
    SelfApprovalError,
    approve_journal,
    create_draft,
    get_journal,
    list_journals,
    post_journal,
    submit_journal,
    void_journal,
)
from app.services.periods import PeriodNotFoundError, PeriodPostingError

router = APIRouter(prefix="/journals", tags=["journals"])


def _to_line_input(line: object) -> JournalLineInput:  # type: ignore[type-arg]
    from app.api.v1.schemas import JournalLineCreate

    assert isinstance(line, JournalLineCreate)
    debit = Decimal(line.debit)
    credit = Decimal(line.credit)
    fx_rate = Decimal(line.fx_rate)
    return JournalLineInput(
        account_id=line.account_id,
        debit=debit,
        credit=credit,
        currency=line.currency,
        fx_rate=fx_rate,
        functional_debit=debit * fx_rate,
        functional_credit=credit * fx_rate,
        description=line.description,
        contact_id=line.contact_id,
    )


async def _load_lines(db: DbSession, journal_id: str) -> list[JournalLine]:  # type: ignore[type-arg]
    result = await db.execute(
        select(JournalLine)
        .where(JournalLine.journal_entry_id == journal_id)
        .order_by(JournalLine.line_no)
    )
    return list(result.scalars().all())


def _journal_response(je: object, lines: list[JournalLine]) -> JournalResponse:  # type: ignore[type-arg]
    from app.api.v1.schemas import JournalLineResponse

    data = JournalResponse.model_validate(je)
    data.lines = [JournalLineResponse.model_validate(ln) for ln in lines]
    return data


@router.post(
    "",
    response_model=JournalResponse,
    status_code=status.HTTP_201_CREATED,
    responses={422: {"model": ProblemDetail}},
)
async def create_journal_endpoint(
    body: JournalCreate,
    db: DbSession,
    tenant_id: TenantId,
    actor_id: ActorId,
    response: Response,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> JournalResponse:
    try:
        line_inputs = [_to_line_input(ln) for ln in body.lines]
        je = await create_draft(
            db,
            tenant_id=tenant_id,
            date_=body.date,
            period_id=body.period_id,
            description=body.description,
            lines=line_inputs,
            source_type=body.source_type,
            source_id=body.source_id,
            actor_id=actor_id,
            idempotency_key=idempotency_key,
            force=body.force,
        )
        await db.commit()
        # If idempotent hit, the journal already existed — return 200 instead of 201
        if idempotency_key is not None and je.idempotency_key == idempotency_key and not db.new:
            response.status_code = status.HTTP_200_OK
    except (JournalBalanceError, ControlAccountError, FutureDateError, InvalidAccountError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except PeriodPostingError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except PeriodNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    lines = await _load_lines(db, je.id)
    return _journal_response(je, lines)


@router.get("", response_model=JournalListResponse)
async def list_journals_endpoint(
    db: DbSession,
    tenant_id: TenantId,
    status_filter: str | None = Query(default=None, alias="status"),
    period_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    cursor: str | None = Query(default=None),
) -> JournalListResponse:
    journals = await list_journals(
        db,
        tenant_id=tenant_id,
        status=status_filter,
        period_id=period_id,
        limit=limit + 1,
        cursor=cursor,
    )
    next_cursor = None
    if len(journals) > limit:
        journals = journals[:limit]
        next_cursor = journals[-1].id
    items = [JournalResponse.model_validate(je) for je in journals]
    return JournalListResponse(items=items, next_cursor=next_cursor)


@router.get("/{journal_id}", response_model=JournalResponse)
async def get_journal_endpoint(
    journal_id: str,
    db: DbSession,
    tenant_id: TenantId,
) -> JournalResponse:
    try:
        je = await get_journal(db, journal_id=journal_id, tenant_id=tenant_id)
    except JournalNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    lines = await _load_lines(db, je.id)
    return _journal_response(je, lines)


@router.post(
    "/{journal_id}/post",
    response_model=JournalResponse,
    responses={422: {"model": ProblemDetail}},
)
async def post_journal_endpoint(
    journal_id: str,
    db: DbSession,
    tenant_id: TenantId,
    actor_id: ActorId,
    admin_override: bool = Query(default=False),
) -> JournalResponse:
    if not actor_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="X-Actor-ID required")
    try:
        je = await post_journal(
            db,
            journal_id=journal_id,
            tenant_id=tenant_id,
            actor_id=actor_id,
            admin_override=admin_override,
        )
        await db.commit()
    except JournalNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except (JournalStatusError, JournalBalanceError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except PeriodPostingError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    lines = await _load_lines(db, je.id)
    return _journal_response(je, lines)


@router.post(
    "/{journal_id}/submit",
    response_model=JournalResponse,
    responses={422: {"model": ProblemDetail}},
)
async def submit_journal_endpoint(
    journal_id: str,
    db: DbSession,
    tenant_id: TenantId,
    actor_id: ActorId,
) -> JournalResponse:
    if not actor_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="X-Actor-ID required")
    try:
        je = await submit_journal(
            db,
            journal_id=journal_id,
            tenant_id=tenant_id,
            actor_id=actor_id,
        )
        await db.commit()
    except JournalNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except JournalStatusError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    lines = await _load_lines(db, je.id)
    return _journal_response(je, lines)


@router.post(
    "/{journal_id}/approve",
    response_model=JournalResponse,
    responses={403: {"model": ProblemDetail}, 422: {"model": ProblemDetail}},
)
async def approve_journal_endpoint(
    journal_id: str,
    db: DbSession,
    tenant_id: TenantId,
    actor_id: ActorId,
    admin_override: bool = Query(default=False),
    body: ApproveRejectRequest | None = None,
) -> JournalResponse:
    if not actor_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="X-Actor-ID required")
    try:
        comment = body.comment if body else None
        je = await approve_journal(
            db,
            journal_id=journal_id,
            tenant_id=tenant_id,
            actor_id=actor_id,
            admin_override=admin_override,
            comment=comment,
        )
        await db.commit()
    except JournalNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except SelfApprovalError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except JournalStatusError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except PeriodPostingError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    lines = await _load_lines(db, je.id)
    return _journal_response(je, lines)


@router.post(
    "/{journal_id}/void",
    response_model=JournalResponse,
    responses={422: {"model": ProblemDetail}},
)
async def void_journal_endpoint(
    journal_id: str,
    body: JournalVoidRequest,
    db: DbSession,
    tenant_id: TenantId,
    actor_id: ActorId,
) -> JournalResponse:
    if not actor_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="X-Actor-ID required")
    try:
        _original, reversal = await void_journal(
            db,
            journal_id=journal_id,
            tenant_id=tenant_id,
            actor_id=actor_id,
            reason=body.reason,
        )
        await db.commit()
    except JournalNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except JournalStatusError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except PeriodPostingError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    lines = await _load_lines(db, reversal.id)
    return _journal_response(reversal, lines)


# ── CSV Import / Template ────────────────────────────────────────────────────

_JOURNAL_REQUIRED = ["date", "description", "account_code", "debit", "credit"]
_JOURNAL_OPTIONAL = ["currency", "fx_rate", "contact_name"]
_JOURNAL_ALL = _JOURNAL_REQUIRED + _JOURNAL_OPTIONAL
_JOURNAL_EXAMPLE = [
    "2025-01-15",
    "Office supplies purchase",
    "6300",
    "500.00",
    "0",
    "USD",
    "1",
    "Office Depot",
]


@router.get("/csv-template")
async def csv_template() -> StreamingResponse:
    """Download a CSV template for journal entry imports."""
    content = generate_template_csv(_JOURNAL_ALL, _JOURNAL_EXAMPLE)
    return StreamingResponse(
        iter([content]),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="journals-template.csv"'},
    )


@router.post("/import", response_model=CsvImportResult, status_code=status.HTTP_201_CREATED)
async def import_journals(
    file: UploadFile,
    db: DbSession,
    tenant_id: TenantId,
    actor_id: ActorId,
    period_id: str = Query(..., description="Period ID to post journal entries into"),
) -> CsvImportResult:
    """Import journal entries from a CSV file.

    Rows with same date + description are grouped into one journal entry
    with multiple lines. Total debits must equal total credits per group.
    """
    content = await file.read()
    rows, errors = await parse_csv(content, _JOURNAL_REQUIRED, _JOURNAL_OPTIONAL)

    if errors and not rows:
        return CsvImportResult(imported=0, skipped=0, errors=errors)

    # Resolve accounts: code -> id
    acct_result = await db.execute(
        select(Account.id, Account.code).where(Account.tenant_id == tenant_id)
    )
    acct_map: dict[str, str] = {code.lower(): aid for aid, code in acct_result}

    # Group rows into journal entries by date + description
    groups: dict[tuple[str, str], list[tuple[int, dict[str, str]]]] = {}
    for row_no, row in enumerate(rows, start=2 + len(errors)):
        key = (row["date"], row["description"])
        groups.setdefault(key, []).append((row_no, row))

    imported = 0
    skipped = 0

    for (date_str, description), group_rows in groups.items():
        try:
            parsed_date = parse_date(date_str)

            line_inputs: list[JournalLineInput] = []
            total_debit = Decimal("0")
            total_credit = Decimal("0")
            line_error = False

            for row_no, row in group_rows:
                acct_code = row["account_code"].lower()
                acct_id = acct_map.get(acct_code)
                if not acct_id:
                    errors.append(f"Row {row_no}: account_code '{row['account_code']}' not found")
                    line_error = True
                    continue

                debit = parse_decimal(row["debit"])
                credit = parse_decimal(row["credit"])
                currency = row.get("currency") or "USD"
                fx_rate = parse_decimal(row.get("fx_rate") or "1")

                total_debit += debit
                total_credit += credit

                line_inputs.append(
                    JournalLineInput(
                        account_id=acct_id,
                        debit=debit,
                        credit=credit,
                        currency=currency,
                        fx_rate=fx_rate,
                        functional_debit=debit * fx_rate,
                        functional_credit=credit * fx_rate,
                        description=description,
                        contact_id=None,
                    )
                )

            if line_error or not line_inputs:
                skipped += len(group_rows)
                continue

            # Validate balance
            if total_debit != total_credit:
                for row_no, _ in group_rows:
                    errors.append(
                        f"Row {row_no}: journal '{description}' is unbalanced "
                        f"(debits={total_debit}, credits={total_credit})"
                    )
                skipped += len(group_rows)
                continue

            await create_draft(
                db,
                tenant_id=tenant_id,
                date_=parsed_date,
                period_id=period_id,
                description=description,
                lines=line_inputs,
                source_type="csv_import",
                actor_id=actor_id,
            )
            imported += 1
        except Exception as exc:
            for row_no, _ in group_rows:
                errors.append(f"Row {row_no}: {exc}")
            skipped += 1

    if imported > 0:
        await db.commit()

    from app.core.logging import get_logger

    get_logger(__name__).info(
        "journals.import.complete",
        tenant_id=tenant_id,
        imported=imported,
        skipped=skipped,
        errors=len(errors),
    )
    return CsvImportResult(imported=imported, skipped=skipped, errors=errors)
