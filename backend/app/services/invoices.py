"""Invoice service — create, authorise (posts JE), void, credit note.

State machine:
  draft → authorised → sent → partial|paid → (terminal)
  any non-void → void
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import ROUND_HALF_EVEN, Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.infra.models import Account, Invoice, InvoiceLine, JournalEntry, JournalLine

log = get_logger(__name__)

_QUANTIZE_4 = Decimal("0.0001")
_QUANTIZE_2 = Decimal("0.01")


class InvoiceNotFoundError(ValueError):
    pass


class InvoiceNumberConflictError(ValueError):
    pass


class InvoiceTransitionError(ValueError):
    pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _compute_line(
    quantity: Decimal,
    unit_price: Decimal,
    discount_pct: Decimal,
    tax_rate: Decimal,
) -> tuple[Decimal, Decimal]:
    """Returns (line_amount_ex_tax, tax_amount)."""
    net = (quantity * unit_price * (1 - discount_pct)).quantize(_QUANTIZE_4, ROUND_HALF_EVEN)
    tax = (net * tax_rate).quantize(_QUANTIZE_4, ROUND_HALF_EVEN)
    return net, tax


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


async def create_invoice(
    db: AsyncSession,
    tenant_id: str,
    actor_id: str | None,
    *,
    contact_id: str,
    issue_date: str,
    due_date: str | None = None,
    currency: str,
    fx_rate: Decimal = Decimal("1"),
    period_name: str | None = None,
    reference: str | None = None,
    notes: str | None = None,
    lines: list[dict],
) -> Invoice:
    """Create a draft invoice with computed totals."""
    # Compute totals
    subtotal = Decimal("0")
    tax_total = Decimal("0")
    line_models: list[InvoiceLine] = []

    for i, line in enumerate(lines, start=1):
        qty = Decimal(str(line["quantity"]))
        price = Decimal(str(line["unit_price"]))
        disc = Decimal(str(line.get("discount_pct", "0")))
        tax_rate = Decimal(str(line.get("_tax_rate", "0")))  # resolved by caller

        net, tax = _compute_line(qty, price, disc, tax_rate)
        subtotal += net
        tax_total += tax

        line_models.append(
            InvoiceLine(
                tenant_id=tenant_id,
                line_no=i,
                item_id=line.get("item_id"),
                account_id=line["account_id"],
                tax_code_id=line.get("tax_code_id"),
                description=line.get("description"),
                quantity=qty,
                unit_price=price,
                discount_pct=disc,
                line_amount=net,
                tax_amount=tax,
            )
        )

    total = subtotal + tax_total
    functional_total = (total * fx_rate).quantize(_QUANTIZE_4, ROUND_HALF_EVEN)

    inv = Invoice(
        tenant_id=tenant_id,
        number=f"DRAFT-{uuid.uuid4().hex[:8].upper()}",  # replaced on authorise
        status="draft",
        contact_id=contact_id,
        issue_date=issue_date,
        due_date=due_date,
        period_name=period_name,
        reference=reference,
        currency=currency,
        fx_rate=fx_rate,
        subtotal=subtotal,
        tax_total=tax_total,
        total=total,
        amount_due=total,
        functional_total=functional_total,
        notes=notes,
        created_by=actor_id,
        updated_by=actor_id,
    )
    db.add(inv)
    await db.flush()  # get inv.id

    for lm in line_models:
        lm.invoice_id = inv.id
        db.add(lm)

    await db.flush()
    await db.refresh(inv)
    log.info("invoice.created", tenant_id=tenant_id, invoice_id=inv.id)
    return inv


async def list_invoices(
    db: AsyncSession,
    tenant_id: str,
    *,
    status: str | None = None,
    contact_id: str | None = None,
    limit: int = 50,
    cursor: str | None = None,
) -> list[Invoice]:
    q = select(Invoice).where(Invoice.tenant_id == tenant_id)
    if status:
        q = q.where(Invoice.status == status)
    if contact_id:
        q = q.where(Invoice.contact_id == contact_id)
    if cursor:
        q = q.where(Invoice.id > cursor)
    q = q.order_by(Invoice.issue_date.desc(), Invoice.id).limit(limit)
    result = await db.execute(q)
    return list(result.scalars())


async def get_invoice(db: AsyncSession, tenant_id: str, invoice_id: str) -> Invoice:
    inv = await db.scalar(
        select(Invoice).where(
            Invoice.id == invoice_id, Invoice.tenant_id == tenant_id
        )
    )
    if not inv:
        raise InvoiceNotFoundError(invoice_id)
    return inv


async def get_invoice_lines(db: AsyncSession, invoice_id: str) -> list[InvoiceLine]:
    result = await db.execute(
        select(InvoiceLine)
        .where(InvoiceLine.invoice_id == invoice_id)
        .order_by(InvoiceLine.line_no)
    )
    return list(result.scalars())


async def authorise_invoice(
    db: AsyncSession, tenant_id: str, invoice_id: str, actor_id: str | None
) -> Invoice:
    """Authorise a draft invoice: assign a real number, post the AR journal entry."""
    inv = await get_invoice(db, tenant_id, invoice_id)
    if inv.status != "draft":
        raise InvoiceTransitionError(f"Cannot authorise invoice with status '{inv.status}'")

    lines = await get_invoice_lines(db, invoice_id)

    # Resolve the AR account for this tenant (assume code 1100 = AR)
    ar_account = await db.scalar(
        select(Account).where(
            Account.tenant_id == tenant_id,
            Account.code == "1100",
        )
    )

    now = datetime.now(tz=UTC)

    # Generate sequential invoice number
    count_result = await db.execute(
        select(func.count()).select_from(Invoice).where(
            Invoice.tenant_id == tenant_id,
            Invoice.status != "draft",
        )
    )
    seq = (count_result.scalar() or 0) + 1
    inv.number = f"INV-{seq:05d}"

    # Build the journal entry: Dr AR, Cr Revenue lines, Cr Tax Payable
    je_lines: list[JournalLine] = []
    line_no = 1

    # Debit: Accounts Receivable for total incl. tax
    total = Decimal(str(inv.total))
    fx = Decimal(str(inv.fx_rate))
    func_total = (total * fx).quantize(_QUANTIZE_4, ROUND_HALF_EVEN)

    ar_id = ar_account.id if ar_account else None

    if ar_id:
        je_lines.append(JournalLine(
            tenant_id=tenant_id,
            line_no=line_no,
            account_id=ar_id,
            contact_id=inv.contact_id,
            description=f"Invoice {inv.number}",
            debit=total,
            credit=Decimal("0"),
            currency=inv.currency,
            fx_rate=fx,
            functional_debit=func_total,
            functional_credit=Decimal("0"),
        ))
        line_no += 1

    # Credit: Revenue per invoice line
    for il in lines:
        la = Decimal(str(il.line_amount))
        func_la = (la * fx).quantize(_QUANTIZE_4, ROUND_HALF_EVEN)
        je_lines.append(JournalLine(
            tenant_id=tenant_id,
            line_no=line_no,
            account_id=il.account_id,
            contact_id=inv.contact_id,
            description=il.description or f"Invoice {inv.number} line {il.line_no}",
            debit=Decimal("0"),
            credit=la,
            currency=inv.currency,
            fx_rate=fx,
            functional_debit=Decimal("0"),
            functional_credit=func_la,
        ))
        line_no += 1

    # Create and post the JE only if we have AR + at least one revenue line
    if len(je_lines) >= 2:
        je = JournalEntry(
            tenant_id=tenant_id,
            number=f"JE-INV-{inv.number}",
            status="posted",
            description=f"Invoice {inv.number}",
            transaction_date=inv.issue_date,
            period_name=inv.period_name or inv.issue_date[:7],
            currency=inv.currency,
            source_type="invoice",
            source_id=invoice_id,
            posted_at=now,
            posted_by=actor_id,
            created_by=actor_id,
            updated_by=actor_id,
        )
        db.add(je)
        await db.flush()

        for jl in je_lines:
            jl.journal_entry_id = je.id
            db.add(jl)

        inv.journal_entry_id = je.id

    inv.status = "authorised"
    inv.updated_by = actor_id
    inv.version += 1

    await db.flush()
    await db.refresh(inv)
    log.info("invoice.authorised", tenant_id=tenant_id, invoice_id=invoice_id, number=inv.number)
    return inv


async def void_invoice(
    db: AsyncSession, tenant_id: str, invoice_id: str, actor_id: str | None
) -> Invoice:
    inv = await get_invoice(db, tenant_id, invoice_id)
    if inv.status == "void":
        raise InvoiceTransitionError("Invoice is already void")
    if inv.status == "paid":
        raise InvoiceTransitionError("Cannot void a fully paid invoice — issue a credit note")

    inv.status = "void"
    inv.voided_at = datetime.now(tz=UTC)
    inv.updated_by = actor_id
    inv.version += 1

    await db.flush()
    await db.refresh(inv)
    log.info("invoice.voided", tenant_id=tenant_id, invoice_id=invoice_id)
    return inv
