"""Sales Documents API — Quotes and Sales Orders."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select

from app.api.v1.deps import ActorId, DbSession, TenantId
from app.infra.models import SalesDocument, SalesDocumentLine

router = APIRouter(prefix="/sales-documents", tags=["sales-documents"])


# ── Schemas ────────────────────────────────────────────────────────────────────


class SalesDocLineIn(BaseModel):
    item_id: str | None = None
    description: str | None = None
    quantity: str = "1"
    unit_price: str = "0"
    tax_rate: str = "0"
    sort_order: int = 0


class SalesDocCreate(BaseModel):
    doc_type: str  # quote | sales_order
    number: str | None = None
    contact_id: str | None = None
    issue_date: str
    expiry_date: str | None = None
    currency: str = "USD"
    reference: str | None = None
    notes: str | None = None
    lines: list[SalesDocLineIn] = []


class SalesDocUpdate(BaseModel):
    status: str | None = None
    reference: str | None = None
    notes: str | None = None
    expiry_date: str | None = None


class SalesDocLineOut(BaseModel):
    id: str
    description: str | None
    quantity: str
    unit_price: str
    tax_rate: str
    line_total: str
    sort_order: int

    model_config = {"from_attributes": True}


class SalesDocOut(BaseModel):
    id: str
    doc_type: str
    number: str
    contact_id: str | None
    issue_date: str
    expiry_date: str | None
    status: str
    currency: str
    subtotal: str
    tax_total: str
    total: str
    reference: str | None
    notes: str | None
    converted_to_id: str | None
    created_at: datetime
    lines: list[SalesDocLineOut] = []

    model_config = {"from_attributes": True}


class SalesDocListOut(BaseModel):
    items: list[SalesDocOut]
    next_cursor: str | None


# ── Helpers ────────────────────────────────────────────────────────────────────


def _compute_totals(lines: list[SalesDocLineIn]) -> tuple[Decimal, Decimal, Decimal]:
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


def _auto_number(doc_type: str, doc_id: str) -> str:
    prefix = "QT" if doc_type == "quote" else "SO"
    return f"{prefix}-{doc_id[:8].upper()}"


async def _to_out(db: Any, doc: SalesDocument) -> SalesDocOut:
    result = await db.execute(
        select(SalesDocumentLine)
        .where(SalesDocumentLine.document_id == doc.id)
        .order_by(SalesDocumentLine.sort_order)
    )
    lines = result.scalars().all()
    lines_out = [
        SalesDocLineOut(
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
    return SalesDocOut(
        id=doc.id,
        doc_type=doc.doc_type,
        number=doc.number,
        contact_id=doc.contact_id,
        issue_date=doc.issue_date,
        expiry_date=doc.expiry_date,
        status=doc.status,
        currency=doc.currency,
        subtotal=str(doc.subtotal),
        tax_total=str(doc.tax_total),
        total=str(doc.total),
        reference=doc.reference,
        notes=doc.notes,
        converted_to_id=doc.converted_to_id,
        created_at=doc.created_at,
        lines=lines_out,
    )


# ── Routes ─────────────────────────────────────────────────────────────────────


@router.post("", response_model=SalesDocOut, status_code=status.HTTP_201_CREATED)
async def create(body: SalesDocCreate, db: DbSession, tenant_id: TenantId, actor_id: ActorId) -> SalesDocOut:
    if body.doc_type not in ("quote", "sales_order"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="doc_type must be quote or sales_order")

    subtotal, tax_total, total = _compute_totals(body.lines)
    now = datetime.now(tz=UTC)

    doc = SalesDocument(
        tenant_id=tenant_id,
        doc_type=body.doc_type,
        number=body.number or "",
        contact_id=body.contact_id,
        issue_date=body.issue_date,
        expiry_date=body.expiry_date,
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
    db.add(doc)
    await db.flush()

    # Set auto-number if not provided
    if not body.number:
        doc.number = _auto_number(body.doc_type, doc.id)

    for line_in in body.lines:
        qty = Decimal(line_in.quantity)
        price = Decimal(line_in.unit_price)
        rate = Decimal(line_in.tax_rate)
        line_total = qty * price * (1 + rate)
        line = SalesDocumentLine(
            tenant_id=tenant_id,
            document_id=doc.id,
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
    await db.refresh(doc)
    return await _to_out(db, doc)


@router.get("", response_model=SalesDocListOut)
async def list_all(
    db: DbSession,
    tenant_id: TenantId,
    doc_type: str | None = Query(default=None),
    contact_id: str | None = Query(default=None),
    limit: int = Query(default=50, le=200),
    cursor: str | None = Query(default=None),
) -> SalesDocListOut:
    q = select(SalesDocument).where(SalesDocument.tenant_id == tenant_id)
    if doc_type:
        q = q.where(SalesDocument.doc_type == doc_type)
    if contact_id:
        q = q.where(SalesDocument.contact_id == contact_id)
    if cursor:
        q = q.where(SalesDocument.id > cursor)
    q = q.order_by(SalesDocument.created_at.desc()).limit(limit + 1)

    result = await db.execute(q)
    docs = list(result.scalars().all())

    next_cursor = None
    if len(docs) > limit:
        next_cursor = docs[limit].id
        docs = docs[:limit]

    items = [await _to_out(db, d) for d in docs]
    return SalesDocListOut(items=items, next_cursor=next_cursor)


@router.get("/{doc_id}", response_model=SalesDocOut)
async def get_one(doc_id: str, db: DbSession, tenant_id: TenantId) -> SalesDocOut:
    result = await db.execute(
        select(SalesDocument).where(
            SalesDocument.id == doc_id, SalesDocument.tenant_id == tenant_id
        )
    )
    doc = result.scalar_one_or_none()
    if doc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Sales document not found")
    return await _to_out(db, doc)


@router.patch("/{doc_id}", response_model=SalesDocOut)
async def update(
    doc_id: str, body: SalesDocUpdate, db: DbSession, tenant_id: TenantId, actor_id: ActorId
) -> SalesDocOut:
    result = await db.execute(
        select(SalesDocument).where(
            SalesDocument.id == doc_id, SalesDocument.tenant_id == tenant_id
        )
    )
    doc = result.scalar_one_or_none()
    if doc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Sales document not found")
    if doc.status == "voided":
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Cannot update a voided document")

    if body.status is not None:
        doc.status = body.status
    if body.reference is not None:
        doc.reference = body.reference
    if body.notes is not None:
        doc.notes = body.notes
    if body.expiry_date is not None:
        doc.expiry_date = body.expiry_date
    doc.updated_at = datetime.now(tz=UTC)
    doc.updated_by = actor_id
    doc.version = (doc.version or 1) + 1

    await db.commit()
    await db.refresh(doc)
    return await _to_out(db, doc)


@router.post("/{doc_id}/convert", response_model=dict)
async def convert(
    doc_id: str, db: DbSession, tenant_id: TenantId, actor_id: ActorId
) -> dict:
    """Convert a quote to a sales_order (or a sales_order to an invoice stub)."""
    result = await db.execute(
        select(SalesDocument).where(
            SalesDocument.id == doc_id, SalesDocument.tenant_id == tenant_id
        )
    )
    source = result.scalar_one_or_none()
    if source is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Sales document not found")
    if source.status == "voided":
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Cannot convert a voided document")
    if source.status == "converted":
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Already converted")

    if source.doc_type == "quote":
        # Convert quote → sales_order
        now = datetime.now(tz=UTC)
        new_doc = SalesDocument(
            tenant_id=tenant_id,
            doc_type="sales_order",
            number="",
            contact_id=source.contact_id,
            issue_date=now.date().isoformat(),
            currency=source.currency,
            subtotal=source.subtotal,
            tax_total=source.tax_total,
            total=source.total,
            reference=source.reference,
            notes=source.notes,
            created_at=now,
            updated_at=now,
            created_by=actor_id,
            updated_by=actor_id,
        )
        db.add(new_doc)
        await db.flush()
        new_doc.number = _auto_number("sales_order", new_doc.id)

        # Copy lines
        lines_result = await db.execute(
            select(SalesDocumentLine).where(SalesDocumentLine.document_id == source.id)
        )
        for src_line in lines_result.scalars().all():
            new_line = SalesDocumentLine(
                tenant_id=tenant_id,
                document_id=new_doc.id,
                item_id=src_line.item_id,
                description=src_line.description,
                quantity=src_line.quantity,
                unit_price=src_line.unit_price,
                tax_rate=src_line.tax_rate,
                line_total=src_line.line_total,
                sort_order=src_line.sort_order,
            )
            db.add(new_line)

        source.status = "converted"
        source.converted_to_id = new_doc.id
        source.updated_at = now
        await db.commit()
        return {"converted_id": new_doc.id, "doc_type": "sales_order"}

    raise HTTPException(
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail="Only quotes can be converted via this endpoint. Use /invoices to create invoice from sales order.",
    )


@router.delete("/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
async def void(doc_id: str, db: DbSession, tenant_id: TenantId, actor_id: ActorId) -> None:
    result = await db.execute(
        select(SalesDocument).where(
            SalesDocument.id == doc_id, SalesDocument.tenant_id == tenant_id
        )
    )
    doc = result.scalar_one_or_none()
    if doc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Sales document not found")
    if doc.status == "voided":
        return
    doc.status = "voided"
    doc.updated_at = datetime.now(tz=UTC)
    doc.updated_by = actor_id
    await db.commit()
