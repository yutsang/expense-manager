"""Invoice template service — CRUD, scheduled generation, save-from-invoice.

Supports recurring invoice templates that auto-generate draft invoices on
a configurable schedule (weekly, monthly, quarterly, annually).
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from dateutil.relativedelta import relativedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.emitter import emit
from app.core.logging import get_logger
from app.infra.models import Invoice, InvoiceLine, InvoiceTemplate
from app.services.invoices import create_invoice

log = get_logger(__name__)


class TemplateNotFoundError(ValueError):
    pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _advance_date(current: date, frequency: str) -> date:
    """Calculate the next generation date based on recurrence frequency."""
    if frequency == "weekly":
        return current + timedelta(weeks=1)
    elif frequency == "monthly":
        return current + relativedelta(months=1)
    elif frequency == "quarterly":
        return current + relativedelta(months=3)
    elif frequency == "annually":
        return current + relativedelta(years=1)
    raise ValueError(f"Unknown frequency: {frequency}")


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


async def create_template(
    db: AsyncSession,
    tenant_id: str,
    actor_id: str | None,
    *,
    contact_id: str,
    name: str,
    currency: str = "USD",
    lines_json: list[dict] | None = None,
    recurrence_frequency: str | None = None,
    next_generation_date: date | None = None,
    end_date: date | None = None,
) -> InvoiceTemplate:
    template = InvoiceTemplate(
        tenant_id=tenant_id,
        contact_id=contact_id,
        name=name,
        currency=currency,
        lines_json=lines_json or [],
        recurrence_frequency=recurrence_frequency,
        next_generation_date=next_generation_date,
        end_date=end_date,
        is_active=True,
        created_by=actor_id,
        updated_by=actor_id,
    )
    db.add(template)
    await db.flush()
    await db.refresh(template)

    await emit(
        db,
        action="invoice_template.created",
        entity_type="invoice_template",
        entity_id=template.id,
        actor_type="user",
        actor_id=actor_id,
        tenant_id=tenant_id,
        after={"name": name, "frequency": recurrence_frequency},
    )
    log.info("invoice_template.created", tenant_id=tenant_id, template_id=template.id)
    return template


async def list_templates(
    db: AsyncSession,
    tenant_id: str,
    *,
    limit: int = 50,
    cursor: str | None = None,
) -> list[InvoiceTemplate]:
    q = select(InvoiceTemplate).where(InvoiceTemplate.tenant_id == tenant_id)
    if cursor:
        q = q.where(InvoiceTemplate.id > cursor)
    q = q.order_by(InvoiceTemplate.created_at.desc(), InvoiceTemplate.id).limit(limit)
    result = await db.execute(q)
    return list(result.scalars())


async def get_template(
    db: AsyncSession, tenant_id: str, template_id: str
) -> InvoiceTemplate:
    template = await db.scalar(
        select(InvoiceTemplate).where(
            InvoiceTemplate.id == template_id,
            InvoiceTemplate.tenant_id == tenant_id,
        )
    )
    if not template:
        raise TemplateNotFoundError(template_id)
    return template


async def update_template(
    db: AsyncSession,
    tenant_id: str,
    template_id: str,
    actor_id: str | None,
    *,
    name: str | None = None,
    contact_id: str | None = None,
    currency: str | None = None,
    lines_json: list[dict] | None = None,
    recurrence_frequency: str | None = None,
    next_generation_date: date | None = None,
    end_date: date | None = None,
    is_active: bool | None = None,
) -> InvoiceTemplate:
    template = await get_template(db, tenant_id, template_id)
    before = {"name": template.name, "is_active": template.is_active}
    if name is not None:
        template.name = name
    if contact_id is not None:
        template.contact_id = contact_id
    if currency is not None:
        template.currency = currency
    if lines_json is not None:
        template.lines_json = lines_json
    if recurrence_frequency is not None:
        template.recurrence_frequency = recurrence_frequency
    if next_generation_date is not None:
        template.next_generation_date = next_generation_date
    if end_date is not None:
        template.end_date = end_date
    if is_active is not None:
        template.is_active = is_active
    template.updated_by = actor_id
    template.updated_at = datetime.now(tz=UTC)
    template.version += 1
    await db.flush()
    await db.refresh(template)

    await emit(
        db,
        action="invoice_template.updated",
        entity_type="invoice_template",
        entity_id=template_id,
        actor_type="user",
        actor_id=actor_id,
        tenant_id=tenant_id,
        before=before,
        after={"name": template.name, "is_active": template.is_active},
    )
    return template


# ---------------------------------------------------------------------------
# Generate invoice from template
# ---------------------------------------------------------------------------


async def _generate_invoice_from_template(
    db: AsyncSession,
    tenant_id: str,
    actor_id: str | None,
    template: InvoiceTemplate,
) -> Invoice:
    """Create a draft invoice from a template's line definitions."""
    today_str = date.today().isoformat()

    # Build lines from template's lines_json
    lines = []
    for line_def in template.lines_json:
        lines.append(
            {
                "account_id": line_def["account_id"],
                "item_id": line_def.get("item_id"),
                "tax_code_id": line_def.get("tax_code_id"),
                "description": line_def.get("description"),
                "quantity": Decimal(str(line_def.get("quantity", "1"))),
                "unit_price": Decimal(str(line_def.get("unit_price", "0"))),
                "discount_pct": Decimal(str(line_def.get("discount_pct", "0"))),
                "_tax_rate": Decimal(str(line_def.get("tax_rate", "0"))),
            }
        )

    invoice = await create_invoice(
        db,
        tenant_id,
        actor_id,
        contact_id=template.contact_id,
        issue_date=today_str,
        currency=template.currency,
        lines=lines,
        reference=f"Generated from template: {template.name}",
    )
    return invoice


async def generate_single_invoice(
    db: AsyncSession,
    tenant_id: str,
    actor_id: str | None,
    template_id: str,
) -> Invoice:
    """Manually generate the next invoice from a template."""
    template = await get_template(db, tenant_id, template_id)
    invoice = await _generate_invoice_from_template(db, tenant_id, actor_id, template)

    template.last_generated_invoice_id = invoice.id
    template.updated_at = datetime.now(tz=UTC)

    # Advance next_generation_date if recurrence is configured
    if template.recurrence_frequency and template.next_generation_date:
        template.next_generation_date = _advance_date(
            template.next_generation_date, template.recurrence_frequency
        )

    await db.flush()

    await emit(
        db,
        action="invoice_template.generated",
        entity_type="invoice_template",
        entity_id=template_id,
        actor_type="user",
        actor_id=actor_id,
        tenant_id=tenant_id,
        after={"invoice_id": invoice.id},
    )
    log.info(
        "invoice_template.generated",
        tenant_id=tenant_id,
        template_id=template_id,
        invoice_id=invoice.id,
    )
    return invoice


async def generate_scheduled_invoices(
    db: AsyncSession,
    tenant_id: str,
) -> list[Invoice]:
    """Find all due templates and generate draft invoices.

    A template is due when:
      - is_active is True
      - next_generation_date <= today
      - end_date is None or end_date >= today
      - recurrence_frequency is set
    """
    today = date.today()
    result = await db.execute(
        select(InvoiceTemplate).where(
            InvoiceTemplate.tenant_id == tenant_id,
            InvoiceTemplate.is_active.is_(True),
            InvoiceTemplate.recurrence_frequency.isnot(None),
            InvoiceTemplate.next_generation_date <= today,
        )
    )
    templates = list(result.scalars())

    generated: list[Invoice] = []
    for template in templates:
        # Skip if past end_date
        if template.end_date and template.end_date < today:
            continue

        invoice = await _generate_invoice_from_template(db, tenant_id, None, template)
        template.last_generated_invoice_id = invoice.id
        template.next_generation_date = _advance_date(
            template.next_generation_date, template.recurrence_frequency
        )
        template.updated_at = datetime.now(tz=UTC)
        generated.append(invoice)

    await db.flush()
    log.info(
        "invoice_templates.scheduled_run",
        tenant_id=tenant_id,
        generated_count=len(generated),
    )
    return generated


# ---------------------------------------------------------------------------
# Save existing invoice as template
# ---------------------------------------------------------------------------


async def save_invoice_as_template(
    db: AsyncSession,
    tenant_id: str,
    actor_id: str | None,
    invoice_id: str,
    name: str,
    recurrence_frequency: str | None = None,
    next_generation_date: date | None = None,
    end_date: date | None = None,
) -> InvoiceTemplate:
    """Create a template from an existing invoice's line items."""
    invoice = await db.scalar(
        select(Invoice).where(Invoice.id == invoice_id, Invoice.tenant_id == tenant_id)
    )
    if not invoice:
        raise ValueError(f"Invoice not found: {invoice_id}")

    # Get invoice lines
    lines_result = await db.execute(
        select(InvoiceLine)
        .where(InvoiceLine.invoice_id == invoice_id)
        .order_by(InvoiceLine.line_no)
    )
    inv_lines = list(lines_result.scalars())

    # Build lines_json from the invoice lines
    lines_json = []
    for il in inv_lines:
        lines_json.append(
            {
                "account_id": il.account_id,
                "item_id": il.item_id,
                "tax_code_id": il.tax_code_id,
                "description": il.description,
                "quantity": str(il.quantity),
                "unit_price": str(il.unit_price),
                "discount_pct": str(il.discount_pct),
            }
        )

    template = await create_template(
        db,
        tenant_id,
        actor_id,
        contact_id=invoice.contact_id,
        name=name,
        currency=invoice.currency,
        lines_json=lines_json,
        recurrence_frequency=recurrence_frequency,
        next_generation_date=next_generation_date,
        end_date=end_date,
    )
    return template
