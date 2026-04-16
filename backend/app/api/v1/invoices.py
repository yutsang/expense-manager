"""Invoices API."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from app.api.v1.deps import ActorId, DbSession, TenantId
from app.api.v1.schemas import (
    InvoiceCreate,
    InvoiceListResponse,
    InvoiceResponse,
)
from app.infra.models import Contact, Invoice
from app.services.email_service import send_email
from app.services.invoices import (
    InvoiceNotFoundError,
    InvoiceTransitionError,
    authorise_invoice,
    create_invoice,
    get_invoice,
    get_invoice_lines,
    list_invoices,
    void_invoice,
)
from app.services.tax_codes import get_tax_code, TaxCodeNotFoundError
from app.workers.reminders import _build_reminder_html

router = APIRouter(prefix="/invoices", tags=["invoices"])


async def _resolve_line_tax(db, tenant_id: str, lines: list) -> list[dict]:
    """Add _tax_rate to each line dict by looking up tax_code_id."""
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


async def _invoice_response(db, inv) -> InvoiceResponse:
    lines = await get_invoice_lines(db, inv.id)
    return InvoiceResponse.model_validate({**inv.__dict__, "lines": lines})


@router.post("", response_model=InvoiceResponse, status_code=status.HTTP_201_CREATED)
async def create(body: InvoiceCreate, db: DbSession, tenant_id: TenantId, actor_id: ActorId):
    lines = await _resolve_line_tax(db, tenant_id, body.lines)
    inv = await create_invoice(
        db, tenant_id, actor_id,
        contact_id=body.contact_id,
        issue_date=str(body.issue_date),
        due_date=str(body.due_date) if body.due_date else None,
        currency=body.currency,
        fx_rate=Decimal(body.fx_rate),
        period_name=body.period_name,
        reference=body.reference,
        notes=body.notes,
        lines=lines,
    )
    await db.commit()
    await db.refresh(inv)
    return await _invoice_response(db, inv)


@router.get("", response_model=InvoiceListResponse)
async def list_all(
    db: DbSession,
    tenant_id: TenantId,
    inv_status: str | None = Query(default=None, alias="status"),
    contact_id: str | None = Query(default=None),
    limit: int = Query(default=50, le=200),
    cursor: str | None = Query(default=None),
):
    items = await list_invoices(db, tenant_id, status=inv_status, contact_id=contact_id, limit=limit + 1, cursor=cursor)
    next_cursor = None
    if len(items) > limit:
        next_cursor = items[limit].id
        items = items[:limit]
    result = []
    for inv in items:
        lines = await get_invoice_lines(db, inv.id)
        result.append(InvoiceResponse.model_validate({**inv.__dict__, "lines": lines}))
    return InvoiceListResponse(items=result, next_cursor=next_cursor)


@router.get("/{invoice_id}", response_model=InvoiceResponse)
async def get_one(invoice_id: str, db: DbSession, tenant_id: TenantId):
    try:
        inv = await get_invoice(db, tenant_id, invoice_id)
        return await _invoice_response(db, inv)
    except InvoiceNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Invoice not found")


@router.post("/{invoice_id}/authorise", response_model=InvoiceResponse)
async def authorise(invoice_id: str, db: DbSession, tenant_id: TenantId, actor_id: ActorId):
    try:
        inv = await authorise_invoice(db, tenant_id, invoice_id, actor_id)
        await db.commit()
        await db.refresh(inv)
        return await _invoice_response(db, inv)
    except InvoiceNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Invoice not found")
    except InvoiceTransitionError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))


@router.post("/{invoice_id}/void", response_model=InvoiceResponse)
async def void(invoice_id: str, db: DbSession, tenant_id: TenantId, actor_id: ActorId):
    try:
        inv = await void_invoice(db, tenant_id, invoice_id, actor_id)
        await db.commit()
        await db.refresh(inv)
        return await _invoice_response(db, inv)
    except InvoiceNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Invoice not found")
    except InvoiceTransitionError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))


@router.post("/{invoice_id}/reminder", status_code=status.HTTP_202_ACCEPTED)
async def send_reminder(invoice_id: str, db: DbSession, tenant_id: TenantId):
    """Manually trigger a payment reminder for a single invoice."""
    # Load invoice scoped to tenant
    result = await db.execute(
        select(Invoice).where(Invoice.id == invoice_id, Invoice.tenant_id == tenant_id)
    )
    inv = result.scalar_one_or_none()
    if inv is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Invoice not found")

    # Load contact
    contact_result = await db.execute(
        select(Contact).where(Contact.id == inv.contact_id, Contact.tenant_id == tenant_id)
    )
    contact = contact_result.scalar_one_or_none()
    if contact is None or not contact.email:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Contact has no email address",
        )

    from datetime import date as _date  # noqa: PLC0415
    due_date_str = str(inv.due_date) if inv.due_date else "N/A"
    if inv.due_date:
        days_overdue = (_date.today() - _date.fromisoformat(str(inv.due_date))).days
    else:
        days_overdue = 0

    html = _build_reminder_html(
        contact_name=contact.name,
        invoice_number=inv.number,
        due_date=due_date_str,
        amount_due=str(inv.amount_due),
        currency=inv.currency,
        days_overdue=days_overdue,
    )
    ok = await send_email(
        to=contact.email,
        subject=f"Payment Reminder: Invoice {inv.number}",
        html=html,
    )
    if ok:
        inv.last_reminder_sent_at = datetime.now(tz=timezone.utc)
        inv.reminder_count = (inv.reminder_count or 0) + 1
        await db.commit()

    return {"sent": ok}
