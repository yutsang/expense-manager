"""Accruals API — CRUD for accruals and prepayments (Issue #42)."""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, HTTPException, Query, status

from app.api.v1.deps import ActorId, DbSession, TenantId
from app.api.v1.schemas import AccrualCreate, AccrualListResponse, AccrualResponse
from app.services.accruals import (
    AccrualNotFoundError,
    create_accrual,
    get_accrual,
    list_accruals,
)
from app.services.periods import PeriodNotFoundError, PeriodPostingError

router = APIRouter(prefix="/accruals", tags=["accruals"])


@router.post("", response_model=AccrualResponse, status_code=status.HTTP_201_CREATED)
async def create(body: AccrualCreate, db: DbSession, tenant_id: TenantId, actor_id: ActorId):
    """Create an accrual or prepayment and post its journal entry."""
    try:
        accrual = await create_accrual(
            db,
            tenant_id=tenant_id,
            actor_id=actor_id,
            accrual_type=body.accrual_type,
            description=body.description,
            amount=Decimal(body.amount),
            currency=body.currency,
            debit_account_id=body.debit_account_id,
            credit_account_id=body.credit_account_id,
            period_id=body.period_id,
        )
        await db.commit()
        return AccrualResponse.model_validate(accrual)
    except PeriodNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Period not found")
    except PeriodPostingError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("", response_model=AccrualListResponse)
async def list_all(
    db: DbSession,
    tenant_id: TenantId,
    period_id: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
):
    """List accruals, optionally filtered by period or status."""
    accruals = await list_accruals(
        db, tenant_id=tenant_id, period_id=period_id, status=status_filter
    )
    items = [AccrualResponse.model_validate(a) for a in accruals]
    return AccrualListResponse(items=items)


@router.get("/{accrual_id}", response_model=AccrualResponse)
async def get_one(accrual_id: str, db: DbSession, tenant_id: TenantId):
    """Get a single accrual by ID."""
    try:
        accrual = await get_accrual(db, tenant_id=tenant_id, accrual_id=accrual_id)
        return AccrualResponse.model_validate(accrual)
    except AccrualNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Accrual not found")
