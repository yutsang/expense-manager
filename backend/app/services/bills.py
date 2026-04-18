"""Bill (purchase bill) service — draft, approve, void.

State machine:
  draft → awaiting_approval → approved → partial|paid → (terminal)
  any non-void → void
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import ROUND_HALF_EVEN, Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.emitter import emit
from app.core.logging import get_logger
from app.infra.models import Account, Bill, BillLine, Contact, JournalEntry, JournalLine

log = get_logger(__name__)

_QUANTIZE_4 = Decimal("0.0001")


class BillNotFoundError(ValueError):
    pass


class BillTransitionError(ValueError):
    pass


class InvalidAccountError(ValueError):
    pass


class ArchivedContactError(ValueError):
    pass


def _compute_line(
    quantity: Decimal,
    unit_price: Decimal,
    discount_pct: Decimal,
    tax_rate: Decimal,
    *,
    is_tax_inclusive: bool = False,
    quantize_tax: bool = True,
) -> tuple[Decimal, Decimal]:
    """Returns (line_amount_ex_tax, tax_amount).

    Mirrors invoices._compute_line — see that docstring for details on
    *is_tax_inclusive* and *quantize_tax*.
    """
    gross = (quantity * unit_price * (1 - discount_pct)).quantize(_QUANTIZE_4, ROUND_HALF_EVEN)

    if is_tax_inclusive and tax_rate != 0:
        net = (gross / (1 + tax_rate)).quantize(_QUANTIZE_4, ROUND_HALF_EVEN)
        tax = gross - net
    else:
        net = gross
        tax = net * tax_rate

    if quantize_tax:
        tax = tax.quantize(_QUANTIZE_4, ROUND_HALF_EVEN)

    return net, tax


async def _get_tenant(db: AsyncSession, tenant_id: str) -> object:
    """Fetch tenant for config lookups (tax rounding policy, etc.)."""
    from app.infra.models import Tenant

    tenant = await db.scalar(select(Tenant).where(Tenant.id == tenant_id))
    return tenant


async def create_bill(
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
    supplier_reference: str | None = None,
    notes: str | None = None,
    lines: list[dict],
    is_tax_inclusive: bool = False,
) -> Bill:
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

    # ── Tax rounding policy (Issue #76) ───────────────────────────────────
    tenant = await _get_tenant(db, tenant_id)
    tax_rounding_policy = getattr(tenant, "tax_rounding_policy", "per_line") if tenant else "per_line"
    quantize_tax = tax_rounding_policy != "per_invoice"

    subtotal = Decimal("0")
    tax_total = Decimal("0")
    line_models: list[BillLine] = []

    for i, line in enumerate(lines, start=1):
        qty = Decimal(str(line["quantity"]))
        price = Decimal(str(line["unit_price"]))
        disc = Decimal(str(line.get("discount_pct", "0")))
        tax_rate = Decimal(str(line.get("_tax_rate", "0")))

        net, tax = _compute_line(
            qty, price, disc, tax_rate,
            is_tax_inclusive=is_tax_inclusive,
            quantize_tax=quantize_tax,
        )
        subtotal += net
        tax_total += tax

        line_models.append(
            BillLine(
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

    # Final quantization for per-invoice rounding
    if not quantize_tax:
        tax_total = tax_total.quantize(_QUANTIZE_4, ROUND_HALF_EVEN)

    total = subtotal + tax_total

    if total <= Decimal("0"):
        raise ValueError("Bill total must be greater than zero")

    functional_total = (total * fx_rate).quantize(_QUANTIZE_4, ROUND_HALF_EVEN)

    # Auto-increment bill number
    count_result = await db.execute(
        select(func.count()).select_from(Bill).where(Bill.tenant_id == tenant_id)
    )
    seq = (count_result.scalar() or 0) + 1

    bill = Bill(
        tenant_id=tenant_id,
        number=f"BILL-{seq:05d}",
        status="draft",
        contact_id=contact_id,
        issue_date=issue_date,
        due_date=due_date,
        period_name=period_name,
        supplier_reference=supplier_reference,
        currency=currency,
        fx_rate=fx_rate,
        is_tax_inclusive=is_tax_inclusive,
        subtotal=subtotal,
        tax_total=tax_total,
        total=total,
        amount_due=total,
        functional_total=functional_total,
        notes=notes,
        created_by=actor_id,
        updated_by=actor_id,
    )
    db.add(bill)
    await db.flush()

    for lm in line_models:
        lm.bill_id = bill.id
        db.add(lm)

    await db.flush()
    await db.refresh(bill)

    await emit(
        db,
        action="bill.created",
        entity_type="bill",
        entity_id=bill.id,
        actor_type="user",
        actor_id=actor_id,
        tenant_id=tenant_id,
        after={"number": bill.number, "status": bill.status, "total": str(bill.total)},
    )
    log.info("bill.created", tenant_id=tenant_id, bill_id=bill.id)
    return bill


async def list_bills(
    db: AsyncSession,
    tenant_id: str,
    *,
    status: str | None = None,
    contact_id: str | None = None,
    due_before: str | None = None,
    due_after: str | None = None,
    limit: int = 50,
    cursor: str | None = None,
) -> list[Bill]:
    q = select(Bill).where(Bill.tenant_id == tenant_id)
    if status:
        q = q.where(Bill.status == status)
    if contact_id:
        q = q.where(Bill.contact_id == contact_id)
    if due_before:
        q = q.where(Bill.due_date <= due_before)
    if due_after:
        q = q.where(Bill.due_date >= due_after)
    if cursor:
        q = q.where(Bill.id > cursor)
    q = q.order_by(Bill.issue_date.desc(), Bill.id).limit(limit)
    result = await db.execute(q)
    return list(result.scalars())


async def get_bill(db: AsyncSession, tenant_id: str, bill_id: str) -> Bill:
    bill = await db.scalar(select(Bill).where(Bill.id == bill_id, Bill.tenant_id == tenant_id))
    if not bill:
        raise BillNotFoundError(bill_id)
    return bill


async def get_bill_lines(db: AsyncSession, bill_id: str) -> list[BillLine]:
    result = await db.execute(
        select(BillLine).where(BillLine.bill_id == bill_id).order_by(BillLine.line_no)
    )
    return list(result.scalars())


async def submit_for_approval(
    db: AsyncSession, tenant_id: str, bill_id: str, actor_id: str | None
) -> Bill:
    bill = await get_bill(db, tenant_id, bill_id)
    if bill.status != "draft":
        raise BillTransitionError(f"Cannot submit bill with status '{bill.status}'")
    bill.status = "awaiting_approval"
    bill.updated_by = actor_id
    bill.version += 1
    await db.flush()
    await db.refresh(bill)
    return bill


async def approve_bill(
    db: AsyncSession, tenant_id: str, bill_id: str, actor_id: str | None
) -> Bill:
    """Approve a bill: post the AP journal entry."""
    bill = await get_bill(db, tenant_id, bill_id)
    if bill.status not in ("draft", "awaiting_approval"):
        raise BillTransitionError(f"Cannot approve bill with status '{bill.status}'")

    before_status = bill.status

    lines = await get_bill_lines(db, bill_id)
    now = datetime.now(tz=UTC)

    # Resolve AP account (code 2000 = Accounts Payable)
    ap_account = await db.scalar(
        select(Account).where(
            Account.tenant_id == tenant_id,
            Account.code == "2000",
        )
    )

    fx = Decimal(str(bill.fx_rate))
    total = Decimal(str(bill.total))
    func_total = (total * fx).quantize(_QUANTIZE_4, ROUND_HALF_EVEN)

    je_lines: list[JournalLine] = []
    line_no = 1

    # Credit: Accounts Payable for total incl. tax
    if ap_account:
        je_lines.append(
            JournalLine(
                tenant_id=tenant_id,
                line_no=line_no,
                account_id=ap_account.id,
                contact_id=bill.contact_id,
                description=f"Bill {bill.number}",
                debit=Decimal("0"),
                credit=total,
                currency=bill.currency,
                fx_rate=fx,
                functional_debit=Decimal("0"),
                functional_credit=func_total,
            )
        )
        line_no += 1

    # Debit: Expense per bill line
    for bl in lines:
        la = Decimal(str(bl.line_amount))
        func_la = (la * fx).quantize(_QUANTIZE_4, ROUND_HALF_EVEN)
        je_lines.append(
            JournalLine(
                tenant_id=tenant_id,
                line_no=line_no,
                account_id=bl.account_id,
                contact_id=bill.contact_id,
                description=bl.description or f"Bill {bill.number} line {bl.line_no}",
                debit=la,
                credit=Decimal("0"),
                currency=bill.currency,
                fx_rate=fx,
                functional_debit=func_la,
                functional_credit=Decimal("0"),
            )
        )
        line_no += 1

    if len(je_lines) >= 2:
        je = JournalEntry(
            tenant_id=tenant_id,
            number=f"JE-BILL-{bill.number}",
            status="posted",
            description=f"Bill {bill.number}",
            transaction_date=bill.issue_date,
            period_name=bill.period_name or bill.issue_date[:7],
            currency=bill.currency,
            source_type="bill",
            source_id=bill_id,
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

        bill.journal_entry_id = je.id

    bill.status = "approved"
    bill.approved_by = actor_id
    bill.approved_at = now
    bill.updated_by = actor_id
    bill.version += 1

    await db.flush()
    await db.refresh(bill)

    await emit(
        db,
        action="bill.approved",
        entity_type="bill",
        entity_id=bill_id,
        actor_type="user",
        actor_id=actor_id,
        tenant_id=tenant_id,
        before={"status": before_status},
        after={"status": "approved"},
    )
    log.info("bill.approved", tenant_id=tenant_id, bill_id=bill_id)
    return bill


async def void_bill(db: AsyncSession, tenant_id: str, bill_id: str, actor_id: str | None) -> Bill:
    bill = await get_bill(db, tenant_id, bill_id)
    if bill.status == "void":
        raise BillTransitionError("Bill is already void")
    if bill.status == "paid":
        raise BillTransitionError("Cannot void a fully paid bill")

    before_status = bill.status
    bill.status = "void"
    bill.updated_by = actor_id
    bill.version += 1
    await db.flush()
    await db.refresh(bill)

    await emit(
        db,
        action="bill.voided",
        entity_type="bill",
        entity_id=bill_id,
        actor_type="user",
        actor_id=actor_id,
        tenant_id=tenant_id,
        before={"status": before_status},
        after={"status": "void"},
    )
    log.info("bill.voided", tenant_id=tenant_id, bill_id=bill_id)
    return bill
