"""Accruals and prepayments service (Issue #42).

Creates accrual/prepayment records with initial JEs, and auto-creates
reversing JEs when a new period opens.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import ROUND_HALF_EVEN, Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.infra.models import Accrual, JournalEntry, JournalLine, Period
from app.services.periods import assert_can_post

log = get_logger(__name__)

_QUANTIZE_4 = Decimal("0.0001")


class AccrualNotFoundError(ValueError):
    pass


async def create_accrual(
    db: AsyncSession,
    *,
    tenant_id: str,
    actor_id: str | None,
    accrual_type: str,
    description: str,
    amount: Decimal,
    currency: str,
    debit_account_id: str,
    credit_account_id: str,
    period_id: str,
) -> Accrual:
    """Create an accrual/prepayment record and post the initial journal entry.

    The JE debits the debit_account and credits the credit_account.
    Raises PeriodPostingError if the period is not open.
    """
    # Validate period is open for posting
    await assert_can_post(db, period_id=period_id, tenant_id=tenant_id)

    now = datetime.now(tz=UTC)
    amount_dec = amount.quantize(_QUANTIZE_4, ROUND_HALF_EVEN)

    # Create the journal entry
    je = JournalEntry(
        id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        number=f"JE-ACC-{uuid.uuid4().hex[:8].upper()}",
        date=now,
        period_id=period_id,
        description=f"{accrual_type.title()}: {description}",
        source_type="accrual",
        status="posted",
        total_debit=amount_dec,
        total_credit=amount_dec,
        currency=currency,
        posted_at=now,
        posted_by=actor_id,
        created_by=actor_id,
        updated_by=actor_id,
    )
    db.add(je)
    await db.flush()

    # Create debit line
    debit_line = JournalLine(
        id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        journal_entry_id=je.id,
        line_no=1,
        account_id=debit_account_id,
        description=f"{accrual_type.title()}: {description}",
        debit=amount_dec,
        credit=Decimal("0"),
        currency=currency,
        fx_rate=Decimal("1"),
        functional_debit=amount_dec,
        functional_credit=Decimal("0"),
    )
    db.add(debit_line)

    # Create credit line
    credit_line = JournalLine(
        id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        journal_entry_id=je.id,
        line_no=2,
        account_id=credit_account_id,
        description=f"{accrual_type.title()}: {description}",
        debit=Decimal("0"),
        credit=amount_dec,
        currency=currency,
        fx_rate=Decimal("1"),
        functional_debit=Decimal("0"),
        functional_credit=amount_dec,
    )
    db.add(credit_line)

    # Create the accrual record
    accrual = Accrual(
        id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        accrual_type=accrual_type,
        description=description,
        amount=amount_dec,
        currency=currency,
        debit_account_id=debit_account_id,
        credit_account_id=credit_account_id,
        period_id=period_id,
        journal_entry_id=je.id,
        status="posted",
        created_by=actor_id,
        updated_by=actor_id,
    )
    db.add(accrual)
    await db.flush()

    log.info(
        "accrual.created",
        tenant_id=tenant_id,
        accrual_id=accrual.id,
        type=accrual_type,
        amount=str(amount_dec),
    )
    return accrual


async def list_accruals(
    db: AsyncSession,
    *,
    tenant_id: str,
    period_id: str | None = None,
    status: str | None = None,
) -> list[Accrual]:
    """List accruals for a tenant, optionally filtered by period or status."""
    q = select(Accrual).where(Accrual.tenant_id == tenant_id)
    if period_id:
        q = q.where(Accrual.period_id == period_id)
    if status:
        q = q.where(Accrual.status == status)
    q = q.order_by(Accrual.created_at.desc())
    result = await db.execute(q)
    return list(result.scalars().all())


async def get_accrual(
    db: AsyncSession, *, tenant_id: str, accrual_id: str
) -> Accrual:
    """Get a single accrual by ID."""
    result = await db.execute(
        select(Accrual).where(
            Accrual.id == accrual_id, Accrual.tenant_id == tenant_id
        )
    )
    accrual = result.scalar_one_or_none()
    if not accrual:
        raise AccrualNotFoundError(f"Accrual not found: {accrual_id}")
    return accrual


async def reverse_accruals(
    db: AsyncSession,
    *,
    tenant_id: str,
    prior_period_id: str,
    new_period: Period,
    actor_id: str | None,
) -> int:
    """Create reversing JEs for all posted accruals from the prior period.

    Called when a new period opens. The reversal JE swaps the debit/credit
    accounts (credits what was debited, debits what was credited).

    Returns the count of accruals reversed.
    """
    # Fetch all posted (non-reversed) accruals from the prior period
    result = await db.execute(
        select(Accrual).where(
            Accrual.tenant_id == tenant_id,
            Accrual.period_id == prior_period_id,
            Accrual.status == "posted",
        )
    )
    accruals = result.scalars().all()

    now = datetime.now(tz=UTC)
    reversed_count = 0

    for accrual in accruals:
        # Skip if already reversed
        if accrual.reversal_journal_entry_id is not None:
            continue

        amount_dec = Decimal(str(accrual.amount))

        # Create the reversing journal entry
        # Reversal swaps debit/credit: credit the debit account, debit the credit account
        rev_je = JournalEntry(
            id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            number=f"JE-REV-{uuid.uuid4().hex[:8].upper()}",
            date=now,
            period_id=new_period.id,
            description=f"Reversal: {accrual.description}",
            source_type="accrual_reversal",
            status="posted",
            total_debit=amount_dec,
            total_credit=amount_dec,
            currency=accrual.currency,
            posted_at=now,
            posted_by=actor_id,
            created_by=actor_id,
            updated_by=actor_id,
        )
        db.add(rev_je)
        await db.flush()

        # Debit line (reverse: debit the credit account)
        rev_debit = JournalLine(
            id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            journal_entry_id=rev_je.id,
            line_no=1,
            account_id=accrual.credit_account_id,
            description=f"Reversal: {accrual.description}",
            debit=amount_dec,
            credit=Decimal("0"),
            currency=accrual.currency,
            fx_rate=Decimal("1"),
            functional_debit=amount_dec,
            functional_credit=Decimal("0"),
        )
        db.add(rev_debit)

        # Credit line (reverse: credit the debit account)
        rev_credit = JournalLine(
            id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            journal_entry_id=rev_je.id,
            line_no=2,
            account_id=accrual.debit_account_id,
            description=f"Reversal: {accrual.description}",
            debit=Decimal("0"),
            credit=amount_dec,
            currency=accrual.currency,
            fx_rate=Decimal("1"),
            functional_debit=Decimal("0"),
            functional_credit=amount_dec,
        )
        db.add(rev_credit)

        # Update the accrual status
        accrual.reversal_journal_entry_id = rev_je.id
        accrual.status = "reversed"
        accrual.updated_at = now
        accrual.updated_by = actor_id
        accrual.version += 1

        reversed_count += 1

    if reversed_count:
        await db.flush()
        log.info(
            "accruals.reversed",
            tenant_id=tenant_id,
            prior_period_id=prior_period_id,
            new_period_id=new_period.id,
            count=reversed_count,
        )

    return reversed_count
