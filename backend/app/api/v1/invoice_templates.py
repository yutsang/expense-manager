"""Invoice Templates API — CRUD, manual generation, save-from-invoice."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status

from app.api.v1.deps import ActorId, DbSession, TenantId
from app.api.v1.schemas import (
    InvoiceResponse,
    InvoiceTemplateCreate,
    InvoiceTemplateListResponse,
    InvoiceTemplateResponse,
    InvoiceTemplateUpdate,
    SaveAsTemplateRequest,
)
from app.services.invoice_templates import (
    TemplateNotFoundError,
    create_template,
    generate_single_invoice,
    get_template,
    list_templates,
    save_invoice_as_template,
    update_template,
)
from app.services.invoices import get_invoice_lines

router = APIRouter(tags=["invoice-templates"])


@router.post(
    "/invoice-templates",
    response_model=InvoiceTemplateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create(
    body: InvoiceTemplateCreate,
    db: DbSession,
    tenant_id: TenantId,
    actor_id: ActorId,
):
    template = await create_template(
        db,
        tenant_id,
        actor_id,
        contact_id=body.contact_id,
        name=body.name,
        currency=body.currency,
        lines_json=body.lines_json,
        recurrence_frequency=body.recurrence_frequency,
        next_generation_date=body.next_generation_date,
        end_date=body.end_date,
    )
    await db.commit()
    await db.refresh(template)
    return InvoiceTemplateResponse.model_validate(template)


@router.get("/invoice-templates", response_model=InvoiceTemplateListResponse)
async def list_all(
    db: DbSession,
    tenant_id: TenantId,
    limit: int = Query(default=50, le=200),
    cursor: str | None = Query(default=None),
):
    items = await list_templates(db, tenant_id, limit=limit + 1, cursor=cursor)
    next_cursor = None
    if len(items) > limit:
        next_cursor = items[limit].id
        items = items[:limit]
    return InvoiceTemplateListResponse(
        items=[InvoiceTemplateResponse.model_validate(t) for t in items],
        next_cursor=next_cursor,
    )


@router.patch(
    "/invoice-templates/{template_id}",
    response_model=InvoiceTemplateResponse,
)
async def patch(
    template_id: str,
    body: InvoiceTemplateUpdate,
    db: DbSession,
    tenant_id: TenantId,
    actor_id: ActorId,
):
    try:
        template = await update_template(
            db,
            tenant_id,
            template_id,
            actor_id,
            name=body.name,
            contact_id=body.contact_id,
            currency=body.currency,
            lines_json=body.lines_json,
            recurrence_frequency=body.recurrence_frequency,
            next_generation_date=body.next_generation_date,
            end_date=body.end_date,
            is_active=body.is_active,
        )
        await db.commit()
        await db.refresh(template)
        return InvoiceTemplateResponse.model_validate(template)
    except TemplateNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Template not found")


@router.post(
    "/invoice-templates/{template_id}/generate",
    response_model=InvoiceResponse,
    status_code=status.HTTP_201_CREATED,
)
async def generate(
    template_id: str,
    db: DbSession,
    tenant_id: TenantId,
    actor_id: ActorId,
):
    """Manually generate the next invoice from a template."""
    try:
        invoice = await generate_single_invoice(db, tenant_id, actor_id, template_id)
        await db.commit()
        await db.refresh(invoice)
        lines = await get_invoice_lines(db, invoice.id)
        return InvoiceResponse.model_validate({**invoice.__dict__, "lines": lines})
    except TemplateNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Template not found")
    except ValueError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc


@router.post(
    "/invoices/{invoice_id}/save-as-template",
    response_model=InvoiceTemplateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def save_as_template(
    invoice_id: str,
    body: SaveAsTemplateRequest,
    db: DbSession,
    tenant_id: TenantId,
    actor_id: ActorId,
):
    """Save an existing invoice as a reusable template."""
    try:
        template = await save_invoice_as_template(
            db,
            tenant_id,
            actor_id,
            invoice_id=invoice_id,
            name=body.name,
            recurrence_frequency=body.recurrence_frequency,
            next_generation_date=body.next_generation_date,
            end_date=body.end_date,
        )
        await db.commit()
        await db.refresh(template)
        return InvoiceTemplateResponse.model_validate(template)
    except ValueError as exc:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
