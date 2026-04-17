"""Expense claims API."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, HTTPException, Query, status

from app.api.v1.deps import ActorId, DbSession, TenantId
from app.api.v1.schemas import (
    ExpenseClaimCreate,
    ExpenseClaimListResponse,
    ExpenseClaimResponse,
)
from app.services.expense_claims import (
    DuplicateReceiptError,
    ExpenseClaimNotFoundError,
    ExpenseClaimTransitionError,
    SelfApprovalError,
    approve_expense_claim,
    create_expense_claim,
    get_expense_claim,
    get_expense_claim_lines,
    list_expense_claims,
    pay_expense_claim,
    reject_expense_claim,
    submit_expense_claim,
)

router = APIRouter(prefix="/expense-claims", tags=["expense-claims"])


async def _claim_response(db, claim) -> ExpenseClaimResponse:
    lines = await get_expense_claim_lines(db, claim.id)
    return ExpenseClaimResponse.model_validate({**claim.__dict__, "lines": lines})


@router.get("", response_model=ExpenseClaimListResponse)
async def list_all(
    db: DbSession,
    tenant_id: TenantId,
    claim_status: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, le=200),
    cursor: str | None = Query(default=None),
):
    items = await list_expense_claims(db, tenant_id, status=claim_status)
    result = []
    for claim in items:
        lines = await get_expense_claim_lines(db, claim.id)
        result.append(ExpenseClaimResponse.model_validate({**claim.__dict__, "lines": lines}))
    return ExpenseClaimListResponse(items=result)


@router.post("", response_model=ExpenseClaimResponse, status_code=status.HTTP_201_CREATED)
async def create(body: ExpenseClaimCreate, db: DbSession, tenant_id: TenantId, actor_id: ActorId):
    data = body.model_dump()
    # Convert date to string for service layer consistency
    data["claim_date"] = (
        str(body.claim_date) if isinstance(body.claim_date, date) else body.claim_date
    )
    try:
        claim = await create_expense_claim(db, tenant_id, actor_id, data)
    except DuplicateReceiptError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    await db.commit()
    await db.refresh(claim)
    return await _claim_response(db, claim)


@router.get("/{claim_id}", response_model=ExpenseClaimResponse)
async def get_one(claim_id: str, db: DbSession, tenant_id: TenantId):
    try:
        claim = await get_expense_claim(db, tenant_id, claim_id)
        return await _claim_response(db, claim)
    except ExpenseClaimNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Expense claim not found")


@router.post("/{claim_id}/submit", response_model=ExpenseClaimResponse)
async def submit(claim_id: str, db: DbSession, tenant_id: TenantId, actor_id: ActorId):
    try:
        claim = await submit_expense_claim(db, tenant_id, actor_id, claim_id)
        await db.commit()
        await db.refresh(claim)
        return await _claim_response(db, claim)
    except ExpenseClaimNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Expense claim not found")
    except ExpenseClaimTransitionError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))


@router.post("/{claim_id}/approve", response_model=ExpenseClaimResponse)
async def approve(claim_id: str, db: DbSession, tenant_id: TenantId, actor_id: ActorId):
    try:
        claim = await approve_expense_claim(db, tenant_id, actor_id, claim_id)
        await db.commit()
        await db.refresh(claim)
        return await _claim_response(db, claim)
    except ExpenseClaimNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Expense claim not found")
    except SelfApprovalError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=str(exc))
    except ExpenseClaimTransitionError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))


@router.post("/{claim_id}/reject", response_model=ExpenseClaimResponse)
async def reject(claim_id: str, db: DbSession, tenant_id: TenantId, actor_id: ActorId):
    try:
        claim = await reject_expense_claim(db, tenant_id, actor_id, claim_id)
        await db.commit()
        await db.refresh(claim)
        return await _claim_response(db, claim)
    except ExpenseClaimNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Expense claim not found")
    except ExpenseClaimTransitionError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))


@router.post("/{claim_id}/pay", response_model=ExpenseClaimResponse)
async def pay(claim_id: str, db: DbSession, tenant_id: TenantId, actor_id: ActorId):
    try:
        claim = await pay_expense_claim(db, tenant_id, actor_id, claim_id)
        await db.commit()
        await db.refresh(claim)
        return await _claim_response(db, claim)
    except ExpenseClaimNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Expense claim not found")
    except ExpenseClaimTransitionError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
