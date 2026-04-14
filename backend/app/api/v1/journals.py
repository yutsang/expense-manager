"""Journals API — create draft, post, void, list, get."""
from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from app.api.v1.deps import ActorId, DbSession, TenantId
from app.api.v1.schemas import (
    JournalCreate,
    JournalListResponse,
    JournalResponse,
    JournalVoidRequest,
    ProblemDetail,
)
from app.domain.ledger.journal import JournalBalanceError, JournalLineInput, JournalStatusError
from app.infra.models import JournalLine
from app.services.journals import (
    JournalNotFoundError,
    create_draft,
    get_journal,
    list_journals,
    post_journal,
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
        )
        await db.commit()
    except JournalBalanceError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
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
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
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
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except PeriodPostingError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    lines = await _load_lines(db, reversal.id)
    return _journal_response(reversal, lines)
