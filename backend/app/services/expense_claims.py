"""Expense claim service — create, submit, approve, reject, pay.

State machine:
  draft → submitted → approved → paid
  submitted → rejected
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.infra.models import (
    Account,
    ExpenseClaim,
    ExpenseClaimLine,
    JournalEntry,
    JournalLine,
    Period,
)
from app.services.periods import PeriodPostingError, get_period_for_date

log = get_logger(__name__)

_QUANTIZE_4 = Decimal("0.0001")


class ExpenseClaimNotFoundError(ValueError):
    pass


class ExpenseClaimTransitionError(ValueError):
    pass


class SelfApprovalError(ValueError):
    pass


class DuplicateReceiptError(ValueError):
    pass


class FutureDateError(ValueError):
    pass


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


async def list_expense_claims(
    db: AsyncSession,
    tenant_id: str,
    *,
    status: str | None = None,
) -> list[ExpenseClaim]:
    q = (
        select(ExpenseClaim)
        .where(ExpenseClaim.tenant_id == tenant_id)
        .order_by(ExpenseClaim.claim_date.desc(), ExpenseClaim.id)
    )
    if status:
        q = q.where(ExpenseClaim.status == status)
    result = await db.execute(q)
    return list(result.scalars())


async def create_expense_claim(
    db: AsyncSession,
    tenant_id: str,
    actor_id: str | None,
    data: dict,
) -> ExpenseClaim:
    """Create a draft expense claim with computed totals."""
    lines_data: list[dict] = data.get("lines", [])

    # ── Duplicate receipt URL detection ──────────────────────────────────
    receipt_urls = [
        line.get("receipt_url")
        for line in lines_data
        if line.get("receipt_url")  # skip None and empty string
    ]

    # Intra-claim: no two lines may share the same receipt_url
    seen: set[str] = set()
    for url in receipt_urls:
        if url in seen:
            raise DuplicateReceiptError(f"Duplicate receipt URL within this claim: {url}")
        seen.add(url)

    # Cross-claim: receipt_url must not exist on any non-rejected claim in this tenant
    if receipt_urls:
        cross_q = (
            select(
                ExpenseClaimLine.claim_id,
                ExpenseClaim.number,
                ExpenseClaimLine.receipt_url,
            )
            .join(ExpenseClaim, ExpenseClaimLine.claim_id == ExpenseClaim.id)
            .where(
                ExpenseClaimLine.tenant_id == tenant_id,
                ExpenseClaimLine.receipt_url.in_(receipt_urls),
                ExpenseClaim.status != "rejected",
            )
        )
        cross_result = await db.execute(cross_q)
        existing = cross_result.first()
        if existing:
            raise DuplicateReceiptError(
                f"Receipt URL '{existing.receipt_url}' is already attached to "
                f"expense claim {existing.number} (id={existing.claim_id})"
            )

    # ── Date validation (Issue #27) ──────────────────────────────────────
    claim_date_str = data["claim_date"]
    claim_date_val = (
        claim_date_str
        if isinstance(claim_date_str, date)
        else date.fromisoformat(str(claim_date_str))
    )

    if claim_date_val > date.today():
        raise FutureDateError(f"Expense claim date {claim_date_val} is in the future")

    period = await get_period_for_date(db, tenant_id=tenant_id, on_date=claim_date_val)
    if period.status in ("hard_closed", "audited"):
        raise PeriodPostingError(
            f"Cannot create expense claim: period '{period.name}' is {period.status}"
        )
    if period.status == "soft_closed":
        log.warning(
            "expense_claim.soft_closed_period",
            tenant_id=tenant_id,
            period=period.name,
            claim_date=str(claim_date_val),
        )

    total_amount = Decimal("0")
    tax_total = Decimal("0")
    line_models: list[ExpenseClaimLine] = []

    for line in lines_data:
        amt = Decimal(str(line["amount"]))
        tax = Decimal(str(line.get("tax_amount", "0")))
        total_amount += amt
        tax_total += tax
        line_models.append(
            ExpenseClaimLine(
                tenant_id=tenant_id,
                account_id=line["account_id"],
                tax_code_id=line.get("tax_code_id"),
                description=line.get("description"),
                amount=amt,
                tax_amount=tax,
                receipt_url=line.get("receipt_url"),
            )
        )

    # Auto-number: EXP-{count+1:06d}
    count_result = await db.execute(
        select(func.count()).select_from(ExpenseClaim).where(ExpenseClaim.tenant_id == tenant_id)
    )
    seq = (count_result.scalar() or 0) + 1

    claim = ExpenseClaim(
        tenant_id=tenant_id,
        number=f"EXP-{seq:06d}",
        contact_id=data["contact_id"],
        status="draft",
        claim_date=data["claim_date"],
        title=data["title"],
        description=data.get("description"),
        currency=data.get("currency", "USD"),
        total_amount=total_amount,
        tax_total=tax_total,
        created_by=actor_id,
        updated_by=actor_id,
    )
    db.add(claim)
    await db.flush()

    for lm in line_models:
        lm.claim_id = claim.id
        db.add(lm)

    await db.flush()
    await db.refresh(claim)
    log.info("expense_claim.created", tenant_id=tenant_id, claim_id=claim.id)
    return claim


async def get_expense_claim(
    db: AsyncSession,
    tenant_id: str,
    claim_id: str,
) -> ExpenseClaim:
    claim = await db.scalar(
        select(ExpenseClaim).where(
            ExpenseClaim.id == claim_id,
            ExpenseClaim.tenant_id == tenant_id,
        )
    )
    if not claim:
        raise ExpenseClaimNotFoundError(claim_id)
    return claim


async def get_expense_claim_lines(
    db: AsyncSession,
    claim_id: str,
) -> list[ExpenseClaimLine]:
    result = await db.execute(select(ExpenseClaimLine).where(ExpenseClaimLine.claim_id == claim_id))
    return list(result.scalars())


# ---------------------------------------------------------------------------
# State transitions
# ---------------------------------------------------------------------------


async def submit_expense_claim(
    db: AsyncSession,
    tenant_id: str,
    actor_id: str | None,
    claim_id: str,
) -> ExpenseClaim:
    """Transition draft → submitted."""
    claim = await get_expense_claim(db, tenant_id, claim_id)
    if claim.status != "draft":
        raise ExpenseClaimTransitionError(
            f"Cannot submit expense claim with status '{claim.status}'"
        )
    claim.status = "submitted"
    claim.updated_by = actor_id
    claim.version += 1
    await db.flush()
    await db.refresh(claim)
    log.info("expense_claim.submitted", tenant_id=tenant_id, claim_id=claim_id)
    return claim


async def approve_expense_claim(
    db: AsyncSession,
    tenant_id: str,
    actor_id: str | None,
    claim_id: str,
) -> ExpenseClaim:
    """Transition submitted → approved."""
    claim = await get_expense_claim(db, tenant_id, claim_id)
    if claim.status != "submitted":
        raise ExpenseClaimTransitionError(
            f"Cannot approve expense claim with status '{claim.status}'"
        )
    if actor_id is not None and actor_id == claim.created_by:
        raise SelfApprovalError(
            "The claim creator cannot approve their own expense claim (segregation of duties)"
        )
    now = datetime.now(tz=UTC)
    claim.status = "approved"
    claim.approved_by = actor_id
    claim.approved_at = now
    claim.updated_by = actor_id
    claim.version += 1
    await db.flush()
    await db.refresh(claim)
    log.info("expense_claim.approved", tenant_id=tenant_id, claim_id=claim_id)
    return claim


async def reject_expense_claim(
    db: AsyncSession,
    tenant_id: str,
    actor_id: str | None,
    claim_id: str,
) -> ExpenseClaim:
    """Transition submitted → rejected."""
    claim = await get_expense_claim(db, tenant_id, claim_id)
    if claim.status != "submitted":
        raise ExpenseClaimTransitionError(
            f"Cannot reject expense claim with status '{claim.status}'"
        )
    claim.status = "rejected"
    claim.updated_by = actor_id
    claim.version += 1
    await db.flush()
    await db.refresh(claim)
    log.info("expense_claim.rejected", tenant_id=tenant_id, claim_id=claim_id)
    return claim


async def pay_expense_claim(
    db: AsyncSession,
    tenant_id: str,
    actor_id: str | None,
    claim_id: str,
) -> ExpenseClaim:
    """Transition approved → paid. Posts a journal entry: DR expense accounts, CR AP."""
    claim = await get_expense_claim(db, tenant_id, claim_id)
    if claim.status != "approved":
        raise ExpenseClaimTransitionError(f"Cannot pay expense claim with status '{claim.status}'")

    lines = await get_expense_claim_lines(db, claim_id)
    now = datetime.now(tz=UTC)

    # Resolve AP account (code 2000 = Accounts Payable)
    ap_account = await db.scalar(
        select(Account).where(
            Account.tenant_id == tenant_id,
            Account.code == "2000",
        )
    )

    total = Decimal(str(claim.total_amount))

    je_lines: list[JournalLine] = []
    line_no = 1

    # Credit: Accounts Payable for total claim
    if ap_account:
        je_lines.append(
            JournalLine(
                tenant_id=tenant_id,
                line_no=line_no,
                account_id=ap_account.id,
                contact_id=claim.contact_id,
                description=f"Expense claim {claim.number}",
                debit=Decimal("0"),
                credit=total,
                currency=claim.currency,
                fx_rate=Decimal("1"),
                functional_debit=Decimal("0"),
                functional_credit=total,
            )
        )
        line_no += 1

    # Debit: Expense account per claim line
    for cl in lines:
        amt = Decimal(str(cl.amount))
        je_lines.append(
            JournalLine(
                tenant_id=tenant_id,
                line_no=line_no,
                account_id=cl.account_id,
                contact_id=claim.contact_id,
                description=cl.description or f"Expense claim {claim.number}",
                debit=amt,
                credit=Decimal("0"),
                currency=claim.currency,
                fx_rate=Decimal("1"),
                functional_debit=amt,
                functional_credit=Decimal("0"),
            )
        )
        line_no += 1

    if len(je_lines) >= 2:
        # Resolve period for today's date
        period = await db.scalar(
            select(Period).where(
                Period.tenant_id == tenant_id,
                func.date(Period.start_date) <= now.date(),
                func.date(Period.end_date) >= now.date(),
            )
        )
        period_id = period.id if period else None

        je = JournalEntry(
            tenant_id=tenant_id,
            number=f"JE-EXP-{claim.number}",
            status="posted",
            description=f"Expense claim {claim.number}: {claim.title}",
            date=now,
            period_id=period_id,
            currency=claim.currency,
            source_type="manual",
            source_id=claim_id,
            total_debit=total,
            total_credit=total,
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

        claim.journal_entry_id = je.id

    claim.status = "paid"
    claim.paid_by = actor_id
    claim.paid_at = now
    claim.updated_by = actor_id
    claim.version += 1

    await db.flush()
    await db.refresh(claim)
    log.info("expense_claim.paid", tenant_id=tenant_id, claim_id=claim_id)
    return claim
