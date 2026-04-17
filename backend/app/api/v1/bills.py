"""Bills API."""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, HTTPException, Query, status

from app.api.v1.deps import ActorId, DbSession, TenantId
from app.api.v1.schemas import (
    BillCreate,
    BillListResponse,
    BillResponse,
)
from app.services.bills import (
    BillNotFoundError,
    BillTransitionError,
    approve_bill,
    create_bill,
    get_bill,
    get_bill_lines,
    list_bills,
    submit_for_approval,
    void_bill,
)
from app.services.tax_codes import TaxCodeNotFoundError, get_tax_code

router = APIRouter(prefix="/bills", tags=["bills"])


async def _resolve_line_tax(db, tenant_id: str, lines: list) -> list[dict]:
    resolved = []
    for line in lines:
        d = line.model_dump()
        d["quantity"] = Decimal(d["quantity"])
        d["unit_price"] = Decimal(d["unit_price"])
        d["discount_pct"] = Decimal(d["discount_pct"])
        if d.get("tax_code_id"):
            try:
                tc = await get_tax_code(db, tenant_id, d["tax_code_id"])
                d["_tax_rate"] = Decimal(str(tc.rate))
            except TaxCodeNotFoundError:
                d["_tax_rate"] = Decimal("0")
        else:
            d["_tax_rate"] = Decimal("0")
        resolved.append(d)
    return resolved


async def _bill_response(db, bill) -> BillResponse:
    lines = await get_bill_lines(db, bill.id)
    return BillResponse.model_validate({**bill.__dict__, "lines": lines})


@router.post("", response_model=BillResponse, status_code=status.HTTP_201_CREATED)
async def create(body: BillCreate, db: DbSession, tenant_id: TenantId, actor_id: ActorId):
    lines = await _resolve_line_tax(db, tenant_id, body.lines)
    try:
        bill = await create_bill(
            db,
            tenant_id,
            actor_id,
            contact_id=body.contact_id,
            issue_date=str(body.issue_date),
            due_date=str(body.due_date) if body.due_date else None,
            currency=body.currency,
            fx_rate=Decimal(body.fx_rate),
            period_name=body.period_name,
            supplier_reference=body.supplier_reference,
            notes=body.notes,
            lines=lines,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    await db.commit()
    await db.refresh(bill)
    return await _bill_response(db, bill)


@router.get("", response_model=BillListResponse)
async def list_all(
    db: DbSession,
    tenant_id: TenantId,
    bill_status: str | None = Query(default=None, alias="status"),
    contact_id: str | None = Query(default=None),
    limit: int = Query(default=50, le=200),
    cursor: str | None = Query(default=None),
):
    items = await list_bills(
        db, tenant_id, status=bill_status, contact_id=contact_id, limit=limit + 1, cursor=cursor
    )
    next_cursor = None
    if len(items) > limit:
        next_cursor = items[limit].id
        items = items[:limit]
    result = []
    for bill in items:
        lines = await get_bill_lines(db, bill.id)
        result.append(BillResponse.model_validate({**bill.__dict__, "lines": lines}))
    return BillListResponse(items=result, next_cursor=next_cursor)


@router.get("/{bill_id}", response_model=BillResponse)
async def get_one(bill_id: str, db: DbSession, tenant_id: TenantId):
    try:
        bill = await get_bill(db, tenant_id, bill_id)
        return await _bill_response(db, bill)
    except BillNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Bill not found")


@router.post("/{bill_id}/submit", response_model=BillResponse)
async def submit(bill_id: str, db: DbSession, tenant_id: TenantId, actor_id: ActorId):
    try:
        bill = await submit_for_approval(db, tenant_id, bill_id, actor_id)
        await db.commit()
        await db.refresh(bill)
        return await _bill_response(db, bill)
    except BillNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Bill not found")
    except BillTransitionError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))


@router.post("/{bill_id}/approve", response_model=BillResponse)
async def approve(bill_id: str, db: DbSession, tenant_id: TenantId, actor_id: ActorId):
    try:
        bill = await approve_bill(db, tenant_id, bill_id, actor_id)
        await db.commit()
        await db.refresh(bill)
        return await _bill_response(db, bill)
    except BillNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Bill not found")
    except BillTransitionError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))


@router.post("/{bill_id}/void", response_model=BillResponse)
async def void(bill_id: str, db: DbSession, tenant_id: TenantId, actor_id: ActorId):
    try:
        bill = await void_bill(db, tenant_id, bill_id, actor_id)
        await db.commit()
        await db.refresh(bill)
        return await _bill_response(db, bill)
    except BillNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Bill not found")
    except BillTransitionError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
