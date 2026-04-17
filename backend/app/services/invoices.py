"""Invoice service — create, authorise (posts JE), void, credit note.

State machine:
  draft → authorised → sent → partial|paid → (terminal)
  draft → awaiting_approval → authorised (when threshold exceeded, requires second user)
  any non-void → void
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import ROUND_HALF_EVEN, Decimal

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.infra.models import (
    Account,
    Contact,
    Invoice,
    InvoiceLine,
    JournalEntry,
    JournalLine,
    Tenant,
)

log = get_logger(__name__)

_QUANTIZE_4 = Decimal("0.0001")
_QUANTIZE_2 = Decimal("0.01")


class InvoiceNotFoundError(ValueError):
    pass


class InvoiceNumberConflictError(ValueError):
    pass


class InvoiceTransitionError(ValueError):
    pass


class InvoiceApprovalError(ValueError):
    pass


class CreditLimitExceededError(ValueError):
    pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def get_tenant(db: AsyncSession, tenant_id: str) -> Tenant:
    tenant = await db.scalar(select(Tenant).where(Tenant.id == tenant_id))
    if not tenant:
        raise ValueError(f"Tenant not found: {tenant_id}")
    return tenant


async def get_contact(db: AsyncSession, tenant_id: str, contact_id: str) -> Contact:
    contact = await db.scalar(
        select(Contact).where(Contact.id == contact_id, Contact.tenant_id == tenant_id)
    )
    if not contact:
        raise ValueError(f"Contact not found: {contact_id}")
    return contact


async def _get_outstanding_invoice_total(
    db: AsyncSession, tenant_id: str, contact_id: str
) -> Decimal:
    """Sum amount_due of all non-void, non-paid invoices for a contact."""
    _OUTSTANDING_STATUSES = ("draft", "awaiting_approval", "authorised", "sent", "partial")
    result = await db.scalar(
        select(func.coalesce(func.sum(Invoice.amount_due), 0)).where(
            Invoice.tenant_id == tenant_id,
            Invoice.contact_id == contact_id,
            Invoice.status.in_(_OUTSTANDING_STATUSES),
        )
    )
    return Decimal(str(result))


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
        select(Invoice).where(Invoice.id == invoice_id, Invoice.tenant_id == tenant_id)
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


async def _post_invoice_journal(
    db: AsyncSession,
    tenant_id: str,
    inv: Invoice,
    lines: list[InvoiceLine],
    actor_id: str | None,
) -> None:
    """Post the AR journal entry for an authorised invoice."""
    ar_account = await db.scalar(
        select(Account).where(
            Account.tenant_id == tenant_id,
            Account.code == "1100",
        )
    )

    now = datetime.now(tz=UTC)

    je_lines: list[JournalLine] = []
    line_no = 1

    total = Decimal(str(inv.total))
    fx = Decimal(str(inv.fx_rate))
    func_total = (total * fx).quantize(_QUANTIZE_4, ROUND_HALF_EVEN)

    ar_id = ar_account.id if ar_account else None

    if ar_id:
        je_lines.append(
            JournalLine(
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
            )
        )
        line_no += 1

    for il in lines:
        la = Decimal(str(il.line_amount))
        func_la = (la * fx).quantize(_QUANTIZE_4, ROUND_HALF_EVEN)
        je_lines.append(
            JournalLine(
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
            )
        )
        line_no += 1

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
            source_id=inv.id,
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


async def authorise_invoice(
    db: AsyncSession,
    tenant_id: str,
    invoice_id: str,
    actor_id: str | None,
    force: bool = False,
) -> Invoice:
    """Authorise a draft invoice: assign a real number, post the AR journal entry.

    If the contact has a credit_limit and the new invoice would push outstanding
    AR above that limit, the authorisation is rejected with CreditLimitExceededError
    (unless force=True).

    If the tenant has an invoice_approval_threshold and the invoice total meets
    or exceeds it, the invoice moves to 'awaiting_approval' instead of
    'authorised'. A second user must then call approve_invoice().
    """
    inv = await get_invoice(db, tenant_id, invoice_id)
    if inv.status != "draft":
        raise InvoiceTransitionError(f"Cannot authorise invoice with status '{inv.status}'")

    lines = await get_invoice_lines(db, invoice_id)

    # Credit limit check
    if not force:
        contact = await get_contact(db, tenant_id, inv.contact_id)
        if contact.credit_limit is not None:
            credit_limit = Decimal(str(contact.credit_limit))
            outstanding = await _get_outstanding_invoice_total(db, tenant_id, inv.contact_id)
            invoice_total_for_check = Decimal(str(inv.total))
            if outstanding + invoice_total_for_check > credit_limit:
                raise CreditLimitExceededError(
                    f"Invoice total {invoice_total_for_check} would bring outstanding AR "
                    f"to {outstanding + invoice_total_for_check}, exceeding credit limit "
                    f"of {credit_limit} for contact {inv.contact_id}"
                )

    # Generate sequential invoice number — atomic increment to avoid race conditions
    seq_result = await db.execute(
        update(Tenant)
        .where(Tenant.id == tenant_id)
        .values(invoice_number_seq=Tenant.invoice_number_seq + 1)
        .returning(Tenant.invoice_number_seq)
    )
    seq = seq_result.scalar_one()
    inv.number = f"INV-{seq:05d}"

    # Check threshold: does this invoice require second-user approval?
    tenant = await get_tenant(db, tenant_id)
    threshold = tenant.invoice_approval_threshold
    invoice_total = Decimal(str(inv.total))

    if threshold is not None and invoice_total >= Decimal(str(threshold)):
        # Large invoice: park in awaiting_approval, do NOT post JE yet
        inv.status = "awaiting_approval"
        inv.authorised_by = actor_id
        inv.updated_by = actor_id
        inv.version += 1
        await db.flush()
        await db.refresh(inv)
        log.info(
            "invoice.awaiting_approval",
            tenant_id=tenant_id,
            invoice_id=invoice_id,
            number=inv.number,
        )
        return inv

    # No threshold or below threshold: single-step authorise + post JE
    await _post_invoice_journal(db, tenant_id, inv, lines, actor_id)

    inv.status = "authorised"
    inv.updated_by = actor_id
    inv.version += 1

    await db.flush()
    await db.refresh(inv)
    log.info("invoice.authorised", tenant_id=tenant_id, invoice_id=invoice_id, number=inv.number)
    return inv


async def approve_invoice(
    db: AsyncSession, tenant_id: str, invoice_id: str, actor_id: str | None
) -> Invoice:
    """Second-step approval for large invoices that exceeded the approval threshold.

    The approver must NOT be the same user who initiated the authorise action.
    """
    inv = await get_invoice(db, tenant_id, invoice_id)
    if inv.status != "awaiting_approval":
        raise InvoiceTransitionError(
            f"Cannot approve invoice with status '{inv.status}'; "
            "only invoices in 'awaiting_approval' can be approved"
        )

    if actor_id and inv.authorised_by == actor_id:
        raise InvoiceApprovalError(
            "Invoice cannot be approved by the same user who initiated authorisation"
        )

    lines = await get_invoice_lines(db, invoice_id)
    await _post_invoice_journal(db, tenant_id, inv, lines, actor_id)

    inv.status = "authorised"
    inv.updated_by = actor_id
    inv.version += 1

    await db.flush()
    await db.refresh(inv)
    log.info("invoice.approved", tenant_id=tenant_id, invoice_id=invoice_id, number=inv.number)
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
