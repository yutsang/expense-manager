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

from app.audit.emitter import emit
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


class InvalidAccountError(ValueError):
    pass


class ArchivedContactError(ValueError):
    pass


class ComplianceRestrictionError(ValueError):
    """Raised when AMLO Cap 615 compliance policy blocks an operation."""

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
    # Validate date order
    if due_date is not None and due_date < issue_date:
        raise ValueError("Due date must be on or after issue date")

    # ── Archived contact guard (Issue #12) ─────────────────────────────────
    contact = await db.scalar(
        select(Contact).where(Contact.id == contact_id, Contact.tenant_id == tenant_id)
    )
    if contact and contact.is_archived:
        raise ArchivedContactError(
            f"Contact {contact_id} is archived and cannot receive new documents"
        )

    # ── Account existence validation (Issue #10) ───────────────────────────
    line_account_ids = list({line["account_id"] for line in lines})
    acct_result = await db.execute(select(Account).where(Account.id.in_(line_account_ids)))
    found_accounts = list(acct_result.scalars().all())
    found_ids = {a.id for a in found_accounts if a.tenant_id == tenant_id}
    missing_ids = set(line_account_ids) - found_ids
    if missing_ids:
        raise InvalidAccountError(
            f"Invalid account IDs for this tenant: {', '.join(sorted(missing_ids))}"
        )

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

    if total <= Decimal("0"):
        raise ValueError("Invoice total must be greater than zero")

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

    await emit(
        db,
        action="invoice.created",
        entity_type="invoice",
        entity_id=inv.id,
        actor_type="user",
        actor_id=actor_id,
        tenant_id=tenant_id,
        after={"number": inv.number, "status": inv.status, "total": str(inv.total)},
    )
    log.info("invoice.created", tenant_id=tenant_id, invoice_id=inv.id)
    return inv


async def list_invoices(
    db: AsyncSession,
    tenant_id: str,
    *,
    status: str | None = None,
    contact_id: str | None = None,
    due_before: str | None = None,
    due_after: str | None = None,
    limit: int = 50,
    cursor: str | None = None,
) -> list[Invoice]:
    q = select(Invoice).where(Invoice.tenant_id == tenant_id)
    if status:
        q = q.where(Invoice.status == status)
    if contact_id:
        q = q.where(Invoice.contact_id == contact_id)
    if due_before:
        q = q.where(Invoice.due_date <= due_before)
    if due_after:
        q = q.where(Invoice.due_date >= due_after)
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

    # AMLO Cap 615 risk rating compliance check (cannot be overridden with force)
    contact = await get_contact(db, tenant_id, inv.contact_id)
    if contact.risk_rating == "unacceptable":
        raise ComplianceRestrictionError(
            "Business relationship restricted by compliance policy — "
            f"contact {inv.contact_id} has risk rating 'unacceptable'"
        )
    if contact.edd_required and not contact.edd_approved_by:
        raise ComplianceRestrictionError(
            "Enhanced Due Diligence (EDD) approval required before invoicing — "
            f"contact {inv.contact_id} has risk rating '{contact.risk_rating}' "
            "and EDD has not been approved by a senior user"
        )

    # Credit limit check
    if not force and contact.credit_limit is not None:
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

        await emit(
            db,
            action="invoice.awaiting_approval",
            entity_type="invoice",
            entity_id=invoice_id,
            actor_type="user",
            actor_id=actor_id,
            tenant_id=tenant_id,
            before={"status": "draft"},
            after={"status": "awaiting_approval", "number": inv.number},
        )
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

    await emit(
        db,
        action="invoice.authorised",
        entity_type="invoice",
        entity_id=invoice_id,
        actor_type="user",
        actor_id=actor_id,
        tenant_id=tenant_id,
        before={"status": "draft"},
        after={"status": "authorised", "number": inv.number},
    )
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

    await emit(
        db,
        action="invoice.approved",
        entity_type="invoice",
        entity_id=invoice_id,
        actor_type="user",
        actor_id=actor_id,
        tenant_id=tenant_id,
        before={"status": "awaiting_approval"},
        after={"status": "authorised", "number": inv.number},
    )
    log.info("invoice.approved", tenant_id=tenant_id, invoice_id=invoice_id, number=inv.number)
    return inv


async def create_credit_note(
    db: AsyncSession,
    tenant_id: str,
    inv: Invoice,
    lines: list[InvoiceLine],
    actor_id: str | None,
) -> tuple[Invoice, JournalEntry]:
    """Create a credit note that reverses an authorised invoice.

    Returns (credit_note_invoice, reversing_journal_entry).
    The credit note is a new Invoice row with status 'credit_note',
    negated amounts, and a reference back to the original invoice.
    The reversing JE credits AR and debits revenue accounts.
    """
    now = datetime.now(tz=UTC)

    total = Decimal(str(inv.total))
    subtotal = Decimal(str(inv.subtotal))
    tax_total = Decimal(str(inv.tax_total))
    fx = Decimal(str(inv.fx_rate))
    func_total = (total * fx).quantize(_QUANTIZE_4, ROUND_HALF_EVEN)

    cn_number = f"CN-{inv.number}"

    # Create the credit note Invoice record with negated amounts
    cn = Invoice(
        tenant_id=tenant_id,
        number=cn_number,
        status="credit_note",
        contact_id=inv.contact_id,
        issue_date=now.strftime("%Y-%m-%d"),
        due_date=inv.due_date,
        period_name=inv.period_name or now.strftime("%Y-%m"),
        reference=f"Credit note for {inv.number}",
        currency=inv.currency,
        fx_rate=fx,
        subtotal=-subtotal,
        tax_total=-tax_total,
        total=-total,
        amount_due=-total,
        functional_total=-func_total,
        credit_note_for_id=inv.id,
        notes=f"Reversing invoice {inv.number}",
        created_by=actor_id,
        updated_by=actor_id,
    )
    db.add(cn)
    await db.flush()

    # Create negated invoice lines on the credit note
    for il in lines:
        la = Decimal(str(il.line_amount))
        ta = Decimal(str(il.tax_amount))
        cn_line = InvoiceLine(
            tenant_id=tenant_id,
            invoice_id=cn.id,
            line_no=il.line_no,
            item_id=il.item_id,
            account_id=il.account_id,
            tax_code_id=il.tax_code_id,
            description=il.description,
            quantity=il.quantity,
            unit_price=il.unit_price,
            discount_pct=il.discount_pct,
            line_amount=-la,
            tax_amount=-ta,
        )
        db.add(cn_line)

    # Post the reversing journal entry
    ar_account = await db.scalar(
        select(Account).where(
            Account.tenant_id == tenant_id,
            Account.code == "1100",
        )
    )

    je_lines: list[JournalLine] = []
    line_no = 1

    ar_id = ar_account.id if ar_account else None

    # Credit AR (reverse the original debit)
    if ar_id:
        je_lines.append(
            JournalLine(
                tenant_id=tenant_id,
                line_no=line_no,
                account_id=ar_id,
                contact_id=inv.contact_id,
                description=f"Credit note {cn_number}",
                debit=Decimal("0"),
                credit=total,
                currency=inv.currency,
                fx_rate=fx,
                functional_debit=Decimal("0"),
                functional_credit=func_total,
            )
        )
        line_no += 1

    # Debit revenue accounts (reverse the original credits)
    for il in lines:
        la = Decimal(str(il.line_amount))
        func_la = (la * fx).quantize(_QUANTIZE_4, ROUND_HALF_EVEN)
        je_lines.append(
            JournalLine(
                tenant_id=tenant_id,
                line_no=line_no,
                account_id=il.account_id,
                contact_id=inv.contact_id,
                description=il.description or f"Credit note {cn_number} line {il.line_no}",
                debit=la,
                credit=Decimal("0"),
                currency=inv.currency,
                fx_rate=fx,
                functional_debit=func_la,
                functional_credit=Decimal("0"),
            )
        )
        line_no += 1

    je = JournalEntry(
        tenant_id=tenant_id,
        number=f"JE-CN-{inv.number}",
        status="posted",
        description=f"Reversing journal for credit note {cn_number}",
        transaction_date=now.strftime("%Y-%m-%d"),
        period_name=inv.period_name or now.strftime("%Y-%m"),
        currency=inv.currency,
        source_type="credit_note",
        source_id=cn.id,
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

    cn.journal_entry_id = je.id
    await db.flush()

    log.info(
        "credit_note.created",
        tenant_id=tenant_id,
        credit_note_id=cn.id,
        original_invoice_id=inv.id,
    )
    return cn, je


async def void_invoice(
    db: AsyncSession, tenant_id: str, invoice_id: str, actor_id: str | None
) -> Invoice:
    inv = await get_invoice(db, tenant_id, invoice_id)
    if inv.status == "void":
        raise InvoiceTransitionError("Invoice is already void")
    if inv.status == "paid":
        raise InvoiceTransitionError("Cannot void a fully paid invoice — issue a credit note")

    before_status = inv.status

    # For invoices that have a posted JE (authorised/sent/partial),
    # create a credit note with a reversing journal entry
    if inv.journal_entry_id is not None:
        lines = await get_invoice_lines(db, invoice_id)
        await create_credit_note(db, tenant_id, inv, lines, actor_id)

    inv.status = "void"
    inv.voided_at = datetime.now(tz=UTC)
    inv.updated_by = actor_id
    inv.version += 1

    await db.flush()
    await db.refresh(inv)

    await emit(
        db,
        action="invoice.voided",
        entity_type="invoice",
        entity_id=invoice_id,
        actor_type="user",
        actor_id=actor_id,
        tenant_id=tenant_id,
        before={"status": before_status},
        after={"status": "void"},
    )
    log.info("invoice.voided", tenant_id=tenant_id, invoice_id=invoice_id)
    return inv


# Statuses from which an invoice can be sent
_SENDABLE_STATUSES = {"authorised", "sent", "partial"}


async def send_invoice(
    db: AsyncSession,
    tenant_id: str,
    invoice_id: str,
    *,
    to: str,
    subject: str | None = None,
    message: str | None = None,
) -> Invoice:
    """Send an invoice via email and mark it as 'sent'.

    Only authorised, sent, or partial invoices can be sent (resending is allowed).
    Draft and void invoices cannot be sent.
    """
    from app.services.email_service import send_email

    inv = await get_invoice(db, tenant_id, invoice_id)

    if inv.status not in _SENDABLE_STATUSES:
        raise InvoiceTransitionError(
            f"Cannot send invoice in '{inv.status}' status — must be authorised first"
        )

    # Verify the contact exists (raises ValueError if not found)
    await get_contact(db, tenant_id, inv.contact_id)

    # Build email subject if not provided
    email_subject = subject or f"Invoice {inv.number}"
    email_html = f"<p>{message or 'Please find your invoice attached.'}</p>"

    ok = await send_email(to=to, subject=email_subject, html=email_html)
    if ok:
        now = datetime.now(tz=UTC)
        inv.sent_at = now
        inv.updated_at = now
        if inv.status == "authorised":
            inv.status = "sent"
        inv.version += 1
        await db.flush()

    log.info("invoice.sent", tenant_id=tenant_id, invoice_id=invoice_id, to=to, ok=ok)
    return inv
