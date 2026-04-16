"""Purchase Orders API."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select

from app.api.v1.deps import ActorId, DbSession, TenantId
from app.infra.models import PurchaseOrder, PurchaseOrderLine

router = APIRouter(prefix="/purchase-orders", tags=["purchase-orders"])


# ── Schemas ────────────────────────────────────────────────────────────────────


class POLineIn(BaseModel):
    item_id: str | None = None
    description: str | None = None
    quantity: str = "1"
    unit_price: str = "0"
    tax_rate: str = "0"
    sort_order: int = 0


class POCreate(BaseModel):
    number: str | None = None
    contact_id: str | None = None
    issue_date: str
    expected_delivery: str | None = None
    currency: str = "USD"
    reference: str | None = None
    notes: str | None = None
    lines: list[POLineIn] = []


class POUpdate(BaseModel):
    status: str | None = None
    reference: str | None = None
    notes: str | None = None
    expected_delivery: str | None = None


class LinkBillBody(BaseModel):
    bill_id: str


class POLineOut(BaseModel):
    id: str
    description: str | None
    quantity: str
    unit_price: str
    tax_rate: str
    line_total: str
    sort_order: int

    model_config = {"from_attributes": True}


class POOut(BaseModel):
    id: str
    number: str
    contact_id: str | None
    issue_date: str
    expected_delivery: str | None
    status: str
    currency: str
    subtotal: str
    tax_total: str
    total: str
    reference: str | None
    notes: str | None
    linked_bill_id: str | None
    created_at: datetime
    lines: list[POLineOut] = []

    model_config = {"from_attributes": True}


class POListOut(BaseModel):
    items: list[POOut]
    next_cursor: str | None


# ── Helpers ────────────────────────────────────────────────────────────────────


def _compute_totals(lines: list[POLineIn]) -> tuple[Decimal, Decimal, Decimal]:
    subtotal = Decimal("0")
    tax_total = Decimal("0")
    for line in lines:
        qty = Decimal(line.quantity)
        price = Decimal(line.unit_price)
        rate = Decimal(line.tax_rate)
        line_amt = qty * price
        subtotal += line_amt
        tax_total += line_amt * rate
    total = subtotal + tax_total
    return subtotal, tax_total, total


def _auto_number(po_id: str) -> str:
    return f"PO-{po_id[:8].upper()}"


async def _to_out(db: Any, po: PurchaseOrder) -> POOut:
    result = await db.execute(
        select(PurchaseOrderLine)
        .where(PurchaseOrderLine.po_id == po.id)
        .order_by(PurchaseOrderLine.sort_order)
    )
    lines = result.scalars().all()
    lines_out = [
        POLineOut(
            id=ln.id,
            description=ln.description,
            quantity=str(ln.quantity),
            unit_price=str(ln.unit_price),
            tax_rate=str(ln.tax_rate),
            line_total=str(ln.line_total),
            sort_order=ln.sort_order,
        )
        for ln in lines
    ]
    return POOut(
        id=po.id,
        number=po.number,
        contact_id=po.contact_id,
        issue_date=po.issue_date,
        expected_delivery=po.expected_delivery,
        status=po.status,
        currency=po.currency,
        subtotal=str(po.subtotal),
        tax_total=str(po.tax_total),
        total=str(po.total),
        reference=po.reference,
        notes=po.notes,
        linked_bill_id=po.linked_bill_id,
        created_at=po.created_at,
        lines=lines_out,
    )


# ── Routes ─────────────────────────────────────────────────────────────────────


@router.post("", response_model=POOut, status_code=status.HTTP_201_CREATED)
async def create(body: POCreate, db: DbSession, tenant_id: TenantId, actor_id: ActorId) -> POOut:
    subtotal, tax_total, total = _compute_totals(body.lines)
    now = datetime.now(tz=UTC)

    po = PurchaseOrder(
        tenant_id=tenant_id,
        number=body.number or "",
        contact_id=body.contact_id,
        issue_date=body.issue_date,
        expected_delivery=body.expected_delivery,
        currency=body.currency,
        subtotal=subtotal,
        tax_total=tax_total,
        total=total,
        reference=body.reference,
        notes=body.notes,
        created_at=now,
        updated_at=now,
        created_by=actor_id,
        updated_by=actor_id,
    )
    db.add(po)
    await db.flush()

    if not body.number:
        po.number = _auto_number(po.id)

    for line_in in body.lines:
        qty = Decimal(line_in.quantity)
        price = Decimal(line_in.unit_price)
        rate = Decimal(line_in.tax_rate)
        line_total = qty * price * (1 + rate)
        line = PurchaseOrderLine(
            tenant_id=tenant_id,
            po_id=po.id,
            item_id=line_in.item_id,
            description=line_in.description,
            quantity=qty,
            unit_price=price,
            tax_rate=rate,
            line_total=line_total,
            sort_order=line_in.sort_order,
        )
        db.add(line)

    await db.commit()
    await db.refresh(po)
    return await _to_out(db, po)


@router.get("", response_model=POListOut)
async def list_all(
    db: DbSession,
    tenant_id: TenantId,
    contact_id: str | None = Query(default=None),
    po_status: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, le=200),
    cursor: str | None = Query(default=None),
) -> POListOut:
    q = select(PurchaseOrder).where(PurchaseOrder.tenant_id == tenant_id)
    if contact_id:
        q = q.where(PurchaseOrder.contact_id == contact_id)
    if po_status:
        q = q.where(PurchaseOrder.status == po_status)
    if cursor:
        q = q.where(PurchaseOrder.id > cursor)
    q = q.order_by(PurchaseOrder.created_at.desc()).limit(limit + 1)

    result = await db.execute(q)
    pos = list(result.scalars().all())

    next_cursor = None
    if len(pos) > limit:
        next_cursor = pos[limit].id
        pos = pos[:limit]

    items = [await _to_out(db, p) for p in pos]
    return POListOut(items=items, next_cursor=next_cursor)


@router.get("/{po_id}", response_model=POOut)
async def get_one(po_id: str, db: DbSession, tenant_id: TenantId) -> POOut:
    result = await db.execute(
        select(PurchaseOrder).where(
            PurchaseOrder.id == po_id, PurchaseOrder.tenant_id == tenant_id
        )
    )
    po = result.scalar_one_or_none()
    if po is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Purchase order not found")
    return await _to_out(db, po)


@router.patch("/{po_id}", response_model=POOut)
async def update(
    po_id: str, body: POUpdate, db: DbSession, tenant_id: TenantId, actor_id: ActorId
) -> POOut:
    result = await db.execute(
        select(PurchaseOrder).where(
            PurchaseOrder.id == po_id, PurchaseOrder.tenant_id == tenant_id
        )
    )
    po = result.scalar_one_or_none()
    if po is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Purchase order not found")
    if po.status == "voided":
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Cannot update a voided PO")

    if body.status is not None:
        po.status = body.status
    if body.reference is not None:
        po.reference = body.reference
    if body.notes is not None:
        po.notes = body.notes
    if body.expected_delivery is not None:
        po.expected_delivery = body.expected_delivery
    po.updated_at = datetime.now(tz=UTC)
    po.updated_by = actor_id
    po.version = (po.version or 1) + 1

    await db.commit()
    await db.refresh(po)
    return await _to_out(db, po)


@router.post("/{po_id}/link-bill", response_model=POOut)
async def link_bill(
    po_id: str, body: LinkBillBody, db: DbSession, tenant_id: TenantId, actor_id: ActorId
) -> POOut:
    result = await db.execute(
        select(PurchaseOrder).where(
            PurchaseOrder.id == po_id, PurchaseOrder.tenant_id == tenant_id
        )
    )
    po = result.scalar_one_or_none()
    if po is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Purchase order not found")
    if po.status == "voided":
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Cannot link bill to a voided PO")

    po.linked_bill_id = body.bill_id
    po.status = "billed"
    po.updated_at = datetime.now(tz=UTC)
    po.updated_by = actor_id
    po.version = (po.version or 1) + 1

    await db.commit()
    await db.refresh(po)
    return await _to_out(db, po)


@router.delete("/{po_id}", status_code=status.HTTP_204_NO_CONTENT)
async def void(po_id: str, db: DbSession, tenant_id: TenantId, actor_id: ActorId) -> None:
    result = await db.execute(
        select(PurchaseOrder).where(
            PurchaseOrder.id == po_id, PurchaseOrder.tenant_id == tenant_id
        )
    )
    po = result.scalar_one_or_none()
    if po is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Purchase order not found")
    if po.status == "voided":
        return
    po.status = "voided"
    po.updated_at = datetime.now(tz=UTC)
    po.updated_by = actor_id
    await db.commit()
