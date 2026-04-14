"""Periods API — list, get, transition."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status

from app.api.v1.deps import ActorId, DbSession, TenantId
from app.api.v1.schemas import PeriodListResponse, PeriodResponse, PeriodTransitionRequest
from app.services.periods import (
    PeriodNotFoundError,
    PeriodPostingError,
    get_period,
    list_periods,
    transition_period,
)
from app.domain.ledger.period import PeriodTransitionError

router = APIRouter(prefix="/periods", tags=["periods"])


@router.get("", response_model=PeriodListResponse)
async def list_periods_endpoint(
    db: DbSession,
    tenant_id: TenantId,
    status: str | None = Query(default=None),
) -> PeriodListResponse:
    periods = await list_periods(db, tenant_id=tenant_id, status=status)
    return PeriodListResponse(items=[PeriodResponse.model_validate(p) for p in periods])


@router.get("/{period_id}", response_model=PeriodResponse)
async def get_period_endpoint(
    period_id: str,
    db: DbSession,
    tenant_id: TenantId,
) -> PeriodResponse:
    try:
        period = await get_period(db, period_id=period_id, tenant_id=tenant_id)
    except PeriodNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return PeriodResponse.model_validate(period)


@router.post("/{period_id}/transition", response_model=PeriodResponse)
async def transition_period_endpoint(
    period_id: str,
    body: PeriodTransitionRequest,
    db: DbSession,
    tenant_id: TenantId,
    actor_id: ActorId,
) -> PeriodResponse:
    if not actor_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="X-Actor-ID required")
    try:
        period = await transition_period(
            db,
            period_id=period_id,
            tenant_id=tenant_id,
            target_status=body.target_status,
            actor_id=actor_id,
            reason=body.reason,
        )
        await db.commit()
    except PeriodNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (PeriodTransitionError, PeriodPostingError) as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return PeriodResponse.model_validate(period)
