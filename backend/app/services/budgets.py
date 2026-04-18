"""Budget service — CRUD for budgets/lines and budget-vs-actual reporting.

Supports monthly budget allocation per GL account, with variance analysis
against actual posted journal entries for a given month.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.emitter import emit
from app.core.logging import get_logger
from app.infra.models import Account, Budget, BudgetLine, JournalEntry, JournalLine

log = get_logger(__name__)

_ZERO = Decimal("0")


class BudgetNotFoundError(ValueError):
    pass


# ---------------------------------------------------------------------------
# CRUD — Budgets
# ---------------------------------------------------------------------------


async def create_budget(
    db: AsyncSession,
    tenant_id: str,
    actor_id: str | None,
    *,
    fiscal_year: int,
    name: str,
    status: str = "draft",
) -> Budget:
    budget = Budget(
        tenant_id=tenant_id,
        fiscal_year=fiscal_year,
        name=name,
        status=status,
        created_by=actor_id,
        updated_by=actor_id,
    )
    db.add(budget)
    await db.flush()
    await db.refresh(budget)

    await emit(
        db,
        action="budget.created",
        entity_type="budget",
        entity_id=budget.id,
        actor_type="user",
        actor_id=actor_id,
        tenant_id=tenant_id,
        after={"name": name, "fiscal_year": fiscal_year, "status": status},
    )
    log.info("budget.created", tenant_id=tenant_id, budget_id=budget.id)
    return budget


async def list_budgets(
    db: AsyncSession,
    tenant_id: str,
    *,
    limit: int = 50,
    cursor: str | None = None,
) -> list[Budget]:
    q = select(Budget).where(Budget.tenant_id == tenant_id)
    if cursor:
        q = q.where(Budget.id > cursor)
    q = q.order_by(Budget.fiscal_year.desc(), Budget.id).limit(limit)
    result = await db.execute(q)
    return list(result.scalars())


async def get_budget(db: AsyncSession, tenant_id: str, budget_id: str) -> Budget:
    budget = await db.scalar(
        select(Budget).where(Budget.id == budget_id, Budget.tenant_id == tenant_id)
    )
    if not budget:
        raise BudgetNotFoundError(budget_id)
    return budget


async def update_budget(
    db: AsyncSession,
    tenant_id: str,
    budget_id: str,
    actor_id: str | None,
    *,
    name: str | None = None,
    status: str | None = None,
) -> Budget:
    budget = await get_budget(db, tenant_id, budget_id)
    before = {"name": budget.name, "status": budget.status}
    if name is not None:
        budget.name = name
    if status is not None:
        budget.status = status
    budget.updated_by = actor_id
    budget.updated_at = datetime.now(tz=UTC)
    budget.version += 1
    await db.flush()
    await db.refresh(budget)

    await emit(
        db,
        action="budget.updated",
        entity_type="budget",
        entity_id=budget_id,
        actor_type="user",
        actor_id=actor_id,
        tenant_id=tenant_id,
        before=before,
        after={"name": budget.name, "status": budget.status},
    )
    log.info("budget.updated", tenant_id=tenant_id, budget_id=budget_id)
    return budget


# ---------------------------------------------------------------------------
# CRUD — Budget Lines
# ---------------------------------------------------------------------------


async def list_budget_lines(
    db: AsyncSession,
    tenant_id: str,
    budget_id: str,
) -> list[BudgetLine]:
    result = await db.execute(
        select(BudgetLine).where(
            BudgetLine.budget_id == budget_id,
            BudgetLine.tenant_id == tenant_id,
        )
    )
    return list(result.scalars())


async def create_budget_line(
    db: AsyncSession,
    tenant_id: str,
    actor_id: str | None,
    *,
    budget_id: str,
    account_id: str,
    months: dict[str, str],
) -> BudgetLine:
    # Verify budget exists
    await get_budget(db, tenant_id, budget_id)

    line = BudgetLine(
        tenant_id=tenant_id,
        budget_id=budget_id,
        account_id=account_id,
        month_1=Decimal(months.get("month_1", "0")),
        month_2=Decimal(months.get("month_2", "0")),
        month_3=Decimal(months.get("month_3", "0")),
        month_4=Decimal(months.get("month_4", "0")),
        month_5=Decimal(months.get("month_5", "0")),
        month_6=Decimal(months.get("month_6", "0")),
        month_7=Decimal(months.get("month_7", "0")),
        month_8=Decimal(months.get("month_8", "0")),
        month_9=Decimal(months.get("month_9", "0")),
        month_10=Decimal(months.get("month_10", "0")),
        month_11=Decimal(months.get("month_11", "0")),
        month_12=Decimal(months.get("month_12", "0")),
        created_by=actor_id,
        updated_by=actor_id,
    )
    db.add(line)
    await db.flush()
    await db.refresh(line)

    await emit(
        db,
        action="budget_line.created",
        entity_type="budget_line",
        entity_id=line.id,
        actor_type="user",
        actor_id=actor_id,
        tenant_id=tenant_id,
        after={"budget_id": budget_id, "account_id": account_id},
    )
    return line


# ---------------------------------------------------------------------------
# Budget vs Actual Report
# ---------------------------------------------------------------------------


async def get_budget_vs_actual(
    db: AsyncSession,
    tenant_id: str,
    budget_id: str,
    month: int,
) -> list[dict]:
    """Return budget vs actual for each budget line account for a given month (1-12).

    Returns a list of dicts with:
      account_id, account_name, budget_amount, actual_amount, variance, variance_pct
    """
    if month < 1 or month > 12:
        raise ValueError("month must be between 1 and 12")

    budget = await get_budget(db, tenant_id, budget_id)

    # Determine the date range for the requested month in the budget's fiscal year
    fiscal_year = budget.fiscal_year
    month_start = datetime(fiscal_year, month, 1, tzinfo=UTC)
    if month == 12:
        month_end = datetime(fiscal_year + 1, 1, 1, tzinfo=UTC)
    else:
        month_end = datetime(fiscal_year, month + 1, 1, tzinfo=UTC)

    # Get all budget lines
    budget_lines = await list_budget_lines(db, tenant_id, budget_id)
    if not budget_lines:
        return []

    # Build a mapping from month number to the column attribute name
    month_attr = f"month_{month}"

    # Get account info for all budget line accounts
    account_ids = [bl.account_id for bl in budget_lines]
    acct_result = await db.execute(
        select(Account).where(Account.id.in_(account_ids), Account.tenant_id == tenant_id)
    )
    accounts_by_id = {a.id: a for a in acct_result.scalars()}

    # Get actual GL totals per account for the month range
    actual_result = await db.execute(
        select(
            JournalLine.account_id,
            func.coalesce(func.sum(JournalLine.functional_debit), 0).label("total_debit"),
            func.coalesce(func.sum(JournalLine.functional_credit), 0).label("total_credit"),
        )
        .join(JournalEntry, JournalLine.journal_entry_id == JournalEntry.id)
        .where(
            JournalLine.tenant_id == tenant_id,
            JournalEntry.status == "posted",
            JournalLine.account_id.in_(account_ids),
            JournalEntry.date >= month_start,
            JournalEntry.date < month_end,
        )
        .group_by(JournalLine.account_id)
    )
    actuals_by_account: dict[str, Decimal] = {}
    for row in actual_result:
        acct = accounts_by_id.get(row.account_id)
        debit = Decimal(str(row.total_debit))
        credit = Decimal(str(row.total_credit))
        # Compute net movement based on normal balance direction
        if acct and acct.normal_balance == "debit":
            actuals_by_account[row.account_id] = debit - credit
        else:
            actuals_by_account[row.account_id] = credit - debit

    # Build response
    result = []
    for bl in budget_lines:
        budget_amount = Decimal(str(getattr(bl, month_attr)))
        actual_amount = actuals_by_account.get(bl.account_id, _ZERO)
        variance = budget_amount - actual_amount
        variance_pct = (
            str((variance / budget_amount * Decimal("100")).quantize(Decimal("0.01")))
            if budget_amount != _ZERO
            else "0.00"
        )
        acct = accounts_by_id.get(bl.account_id)
        result.append(
            {
                "account_id": bl.account_id,
                "account_name": acct.name if acct else "",
                "budget_amount": str(budget_amount),
                "actual_amount": str(actual_amount),
                "variance": str(variance),
                "variance_pct": variance_pct,
            }
        )

    return result
