"""Payments service — create, list, allocate, void.

State machine:
  pending → applied (when fully allocated)
  any non-voided → voided
"""
from __future__ import annotations

from decimal import ROUND_HALF_EVEN, Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.infra.models import Bill, Contact, Invoice, Payment, PaymentAllocation

log = get_logger(__name__)

_QUANTIZE_4 = Decimal("0.0001")


class PaymentNotFoundError(ValueError):
    pass


class PaymentTransitionError(ValueError):
    pass


class AllocationError(ValueError):
    pass


async def create_payment(
    db: AsyncSession,
    tenant_id: str,
    actor_id: str | None,
    *,
    payment_type: str,
    contact_id: str,
    amount: Decimal,
    currency: str,
    fx_rate: Decimal = Decimal("1"),
    payment_date: str,
    reference: str | None = None,
    bank_account_ref: str | None = None,
) -> Payment:
    """Create a new payment. Validates the contact exists for this tenant."""
    contact = await db.scalar(
        select(Contact).where(
            Contact.id == contact_id,
            Contact.tenant_id == tenant_id,
        )
    )
    if contact is None:
        raise AllocationError(f"Contact not found: {contact_id}")

    count_result = await db.execute(
        select(func.count()).select_from(Payment).where(Payment.tenant_id == tenant_id)
    )
    seq = (count_result.scalar() or 0) + 1

    amount_q = amount.quantize(_QUANTIZE_4, ROUND_HALF_EVEN)
    functional_amount = (amount_q * fx_rate).quantize(_QUANTIZE_4, ROUND_HALF_EVEN)

    payment = Payment(
        tenant_id=tenant_id,
        number=f"PAY-{seq:06d}",
        payment_type=payment_type,
        status="pending",
        contact_id=contact_id,
        payment_date=payment_date,
        amount=amount_q,
        currency=currency,
        fx_rate=fx_rate,
        functional_amount=functional_amount,
        reference=reference,
        created_by=actor_id,
        updated_by=actor_id,
    )
    db.add(payment)
    await db.flush()
    await db.refresh(payment)
    log.info("payment.created", tenant_id=tenant_id, payment_id=payment.id)
    return payment


async def list_payments(
    db: AsyncSession,
    tenant_id: str,
    *,
    limit: int = 50,
    offset: int = 0,
    payment_type: str | None = None,
    status: str | None = None,
) -> tuple[list[Payment], int]:
    q = select(Payment).where(Payment.tenant_id == tenant_id)
    if payment_type:
        q = q.where(Payment.payment_type == payment_type)
    if status:
        q = q.where(Payment.status == status)

    count_q = select(func.count()).select_from(q.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    q = q.order_by(Payment.payment_date.desc(), Payment.id).limit(limit).offset(offset)
    result = await db.execute(q)
    return list(result.scalars()), total


async def get_payment(db: AsyncSession, tenant_id: str, payment_id: str) -> Payment:
    payment = await db.scalar(
        select(Payment).where(
            Payment.id == payment_id,
            Payment.tenant_id == tenant_id,
        )
    )
    if not payment:
        raise PaymentNotFoundError(payment_id)
    return payment


async def allocate_payment(
    db: AsyncSession,
    tenant_id: str,
    actor_id: str | None,
    *,
    payment_id: str,
    invoice_id: str | None = None,
    bill_id: str | None = None,
    amount_applied: Decimal,
) -> PaymentAllocation:
    """Allocate a payment to an invoice or bill.

    Updates the target document's amount_due. Marks the payment as 'applied'
    if total allocated equals the payment amount.
    """
    if not (invoice_id or bill_id):
        raise AllocationError("Either invoice_id or bill_id must be provided")
    if invoice_id and bill_id:
        raise AllocationError("Only one of invoice_id or bill_id may be provided")

    payment = await get_payment(db, tenant_id, payment_id)
    if payment.status == "voided":
        raise PaymentTransitionError("Cannot allocate a voided payment")

    amount_q = amount_applied.quantize(_QUANTIZE_4, ROUND_HALF_EVEN)
    if amount_q <= Decimal("0"):
        raise AllocationError("amount_applied must be positive")

    # Verify the target document belongs to this tenant and get its amount_due
    if invoice_id:
        doc = await db.scalar(
            select(Invoice).where(
                Invoice.id == invoice_id,
                Invoice.tenant_id == tenant_id,
            )
        )
        if doc is None:
            raise AllocationError(f"Invoice not found: {invoice_id}")
        doc_amount_due = Decimal(str(doc.amount_due))
        if amount_q > doc_amount_due:
            raise AllocationError(
                f"amount_applied {amount_q} exceeds invoice amount_due {doc_amount_due}"
            )
    else:
        doc = await db.scalar(
            select(Bill).where(
                Bill.id == bill_id,
                Bill.tenant_id == tenant_id,
            )
        )
        if doc is None:
            raise AllocationError(f"Bill not found: {bill_id}")
        doc_amount_due = Decimal(str(doc.amount_due))
        if amount_q > doc_amount_due:
            raise AllocationError(
                f"amount_applied {amount_q} exceeds bill amount_due {doc_amount_due}"
            )

    allocation = PaymentAllocation(
        tenant_id=tenant_id,
        payment_id=payment_id,
        invoice_id=invoice_id,
        bill_id=bill_id,
        amount=amount_q,
        currency=payment.currency,
        created_by=actor_id,
    )
    db.add(allocation)

    # Reduce amount_due on the target document
    new_due = (doc_amount_due - amount_q).quantize(_QUANTIZE_4, ROUND_HALF_EVEN)
    doc.amount_due = new_due  # type: ignore[assignment]

    # Check if payment is now fully allocated
    existing_allocs_result = await db.execute(
        select(func.coalesce(func.sum(PaymentAllocation.amount), Decimal("0"))).where(
            PaymentAllocation.payment_id == payment_id
        )
    )
    existing_total = Decimal(str(existing_allocs_result.scalar() or "0"))
    new_total_allocated = existing_total + amount_q
    payment_amount = Decimal(str(payment.amount))

    if new_total_allocated >= payment_amount:
        payment.status = "applied"
        payment.version += 1

    payment.updated_by = actor_id

    await db.flush()
    await db.refresh(allocation)
    log.info(
        "payment.allocated",
        tenant_id=tenant_id,
        payment_id=payment_id,
        invoice_id=invoice_id,
        bill_id=bill_id,
    )
    return allocation


async def void_payment(
    db: AsyncSession,
    tenant_id: str,
    actor_id: str | None,
    *,
    payment_id: str,
    reason: str,
) -> Payment:
    """Void a payment and reverse all its allocations."""
    payment = await get_payment(db, tenant_id, payment_id)
    if payment.status == "voided":
        raise PaymentTransitionError("Payment is already voided")

    # Reverse all allocations — restore amount_due on each target document
    allocs_result = await db.execute(
        select(PaymentAllocation).where(PaymentAllocation.payment_id == payment_id)
    )
    allocs = list(allocs_result.scalars())

    for alloc in allocs:
        alloc_amount = Decimal(str(alloc.amount))
        if alloc.invoice_id:
            inv = await db.scalar(
                select(Invoice).where(Invoice.id == alloc.invoice_id)
            )
            if inv is not None:
                inv.amount_due = (Decimal(str(inv.amount_due)) + alloc_amount).quantize(
                    _QUANTIZE_4, ROUND_HALF_EVEN
                )  # type: ignore[assignment]
        elif alloc.bill_id:
            bill = await db.scalar(
                select(Bill).where(Bill.id == alloc.bill_id)
            )
            if bill is not None:
                bill.amount_due = (Decimal(str(bill.amount_due)) + alloc_amount).quantize(
                    _QUANTIZE_4, ROUND_HALF_EVEN
                )  # type: ignore[assignment]

    payment.status = "voided"
    payment.updated_by = actor_id
    payment.version += 1

    await db.flush()
    await db.refresh(payment)
    log.info("payment.voided", tenant_id=tenant_id, payment_id=payment_id, reason=reason)
    return payment
