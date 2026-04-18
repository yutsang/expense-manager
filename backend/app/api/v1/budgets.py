"""Budgets API — CRUD and budget-vs-actual reporting."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status

from app.api.v1.deps import ActorId, DbSession, TenantId
from app.api.v1.schemas import (
    BudgetCreate,
    BudgetLineCreate,
    BudgetLineListResponse,
    BudgetLineResponse,
    BudgetListResponse,
    BudgetResponse,
    BudgetUpdate,
)
from app.services.budgets import (
    BudgetNotFoundError,
    create_budget,
    create_budget_line,
    get_budget,
    list_budget_lines,
    list_budgets,
    update_budget,
)

router = APIRouter(prefix="/budgets", tags=["budgets"])


@router.post("", response_model=BudgetResponse, status_code=status.HTTP_201_CREATED)
async def create(body: BudgetCreate, db: DbSession, tenant_id: TenantId, actor_id: ActorId):
    budget = await create_budget(
        db,
        tenant_id,
        actor_id,
        fiscal_year=body.fiscal_year,
        name=body.name,
        status=body.status,
    )
    await db.commit()
    await db.refresh(budget)
    return BudgetResponse.model_validate(budget)


@router.get("", response_model=BudgetListResponse)
async def list_all(
    db: DbSession,
    tenant_id: TenantId,
    limit: int = Query(default=50, le=200),
    cursor: str | None = Query(default=None),
):
    items = await list_budgets(db, tenant_id, limit=limit + 1, cursor=cursor)
    next_cursor = None
    if len(items) > limit:
        next_cursor = items[limit].id
        items = items[:limit]
    return BudgetListResponse(
        items=[BudgetResponse.model_validate(b) for b in items],
        next_cursor=next_cursor,
    )


@router.get("/{budget_id}", response_model=BudgetResponse)
async def get_one(budget_id: str, db: DbSession, tenant_id: TenantId):
    try:
        budget = await get_budget(db, tenant_id, budget_id)
        return BudgetResponse.model_validate(budget)
    except BudgetNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Budget not found")


@router.patch("/{budget_id}", response_model=BudgetResponse)
async def patch(
    budget_id: str,
    body: BudgetUpdate,
    db: DbSession,
    tenant_id: TenantId,
    actor_id: ActorId,
):
    try:
        budget = await update_budget(
            db,
            tenant_id,
            budget_id,
            actor_id,
            name=body.name,
            status=body.status,
        )
        await db.commit()
        await db.refresh(budget)
        return BudgetResponse.model_validate(budget)
    except BudgetNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Budget not found")


# ── Budget Lines ─────────────────────────────────────────────────────────────


@router.get("/{budget_id}/lines", response_model=BudgetLineListResponse)
async def get_lines(budget_id: str, db: DbSession, tenant_id: TenantId):
    try:
        await get_budget(db, tenant_id, budget_id)
    except BudgetNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Budget not found")
    lines = await list_budget_lines(db, tenant_id, budget_id)
    return BudgetLineListResponse(
        items=[BudgetLineResponse.model_validate(bl) for bl in lines],
    )


@router.post(
    "/{budget_id}/lines",
    response_model=BudgetLineResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_line(
    budget_id: str,
    body: BudgetLineCreate,
    db: DbSession,
    tenant_id: TenantId,
    actor_id: ActorId,
):
    try:
        months = body.model_dump(exclude={"account_id"})
        line = await create_budget_line(
            db,
            tenant_id,
            actor_id,
            budget_id=budget_id,
            account_id=body.account_id,
            months=months,
        )
        await db.commit()
        await db.refresh(line)
        return BudgetLineResponse.model_validate(line)
    except BudgetNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Budget not found")
