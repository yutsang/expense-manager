"""Periods API — list, get, create, transition."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel

from app.api.v1.deps import ActorId, DbSession, TenantId
from app.api.v1.schemas import (
    PeriodListResponse,
    PeriodResponse,
    PeriodTransitionRequest,
    PeriodTransitionWarningResponse,
)
from app.domain.ledger.period import PeriodTransitionError
from app.services.periods import (
    PeriodNotFoundError,
    PeriodPostingError,
    get_period,
    list_periods,
    provision_periods,
    transition_period,
)

router = APIRouter(prefix="/periods", tags=["periods"])


class PeriodProvisionRequest(BaseModel):
    months: int = 24


@router.post("/provision", response_model=PeriodListResponse)
async def provision_periods_endpoint(
    body: PeriodProvisionRequest,
    db: DbSession,
    tenant_id: TenantId,
) -> PeriodListResponse:
    """Create monthly periods for this tenant (idempotent). Call once on onboarding."""
    from sqlalchemy import select as sa_select

    from app.infra.models import Tenant as TenantModel

    result = await db.execute(sa_select(TenantModel).where(TenantModel.id == tenant_id))
    tenant = result.scalar_one_or_none()
    currency = tenant.functional_currency if tenant else "USD"
    fiscal_start = tenant.fiscal_year_start_month if tenant else 1
    from_date = date.today().replace(day=1)
    # Go back 3 months so past data is covered
    m = from_date.month - 3
    y = from_date.year
    while m <= 0:
        m += 12
        y -= 1
    from_date = date(y, m, 1)
    await provision_periods(
        db,
        tenant_id=tenant_id,
        functional_currency=currency,
        fiscal_year_start_month=fiscal_start,
        from_date=from_date,
        months=body.months,
    )
    await db.commit()
    all_periods = await list_periods(db, tenant_id=tenant_id)
    return PeriodListResponse(items=[PeriodResponse.model_validate(p) for p in all_periods])


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


@router.post(
    "/{period_id}/transition",
    response_model=PeriodResponse | PeriodTransitionWarningResponse,
)
async def transition_period_endpoint(
    period_id: str,
    body: PeriodTransitionRequest,
    db: DbSession,
    tenant_id: TenantId,
    actor_id: ActorId,
) -> PeriodResponse | PeriodTransitionWarningResponse:
    if not actor_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="X-Actor-ID required")
    try:
        result = await transition_period(
            db,
            period_id=period_id,
            tenant_id=tenant_id,
            target_status=body.target_status,
            actor_id=actor_id,
            reason=body.reason,
            force=body.force,
        )
        if isinstance(result, dict):
            return PeriodTransitionWarningResponse(**result)
        await db.commit()
    except PeriodNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (PeriodTransitionError, PeriodPostingError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    return PeriodResponse.model_validate(result)
