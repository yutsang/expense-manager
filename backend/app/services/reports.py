"""Core reporting service — Trial Balance, General Ledger detail.

All queries read from posted journal lines only (status='posted').
Report rows use Decimal for all amounts — never float.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infra.models import Account, JournalEntry, JournalLine


@dataclass
class TrialBalanceRow:
    account_id: str
    code: str
    name: str
    type: str
    normal_balance: str
    total_debit: Decimal
    total_credit: Decimal

    @property
    def balance(self) -> Decimal:
        """Net balance in normal-balance direction."""
        if self.normal_balance == "debit":
            return self.total_debit - self.total_credit
        return self.total_credit - self.total_debit


@dataclass
class TrialBalanceReport:
    as_of: date
    tenant_id: str
    rows: list[TrialBalanceRow]
    generated_at: datetime

    @property
    def total_debit(self) -> Decimal:
        return sum(r.total_debit for r in self.rows)

    @property
    def total_credit(self) -> Decimal:
        return sum(r.total_credit for r in self.rows)

    @property
    def is_balanced(self) -> bool:
        return self.total_debit == self.total_credit


@dataclass
class GLLine:
    date: date
    journal_number: str
    journal_id: str
    description: str
    debit: Decimal
    credit: Decimal
    running_balance: Decimal


@dataclass
class GLReport:
    account_id: str
    account_code: str
    account_name: str
    normal_balance: str
    from_date: date
    to_date: date
    opening_balance: Decimal
    lines: list[GLLine]
    closing_balance: Decimal


async def trial_balance(
    db: AsyncSession,
    *,
    tenant_id: str,
    as_of: date,
) -> TrialBalanceReport:
    """Return trial balance as of `as_of` (all posted entries on or before that date)."""
    as_of_dt = datetime.combine(as_of, datetime.max.time()).replace(tzinfo=UTC)

    # Sum functional_debit and functional_credit per account from posted JEs
    result = await db.execute(
        select(
            JournalLine.account_id,
            func.sum(JournalLine.functional_debit).label("total_debit"),
            func.sum(JournalLine.functional_credit).label("total_credit"),
        )
        .join(JournalEntry, JournalLine.journal_entry_id == JournalEntry.id)
        .where(
            JournalLine.tenant_id == tenant_id,
            JournalEntry.status == "posted",
            JournalEntry.date <= as_of_dt,
        )
        .group_by(JournalLine.account_id)
    )
    rows_raw = result.all()

    # Fetch account metadata
    account_ids = [r.account_id for r in rows_raw]
    accts_result = await db.execute(
        select(Account).where(Account.id.in_(account_ids))
    )
    accts = {a.id: a for a in accts_result.scalars().all()}

    rows = [
        TrialBalanceRow(
            account_id=r.account_id,
            code=accts[r.account_id].code if r.account_id in accts else "?",
            name=accts[r.account_id].name if r.account_id in accts else "?",
            type=accts[r.account_id].type if r.account_id in accts else "?",
            normal_balance=accts[r.account_id].normal_balance if r.account_id in accts else "debit",
            total_debit=Decimal(str(r.total_debit or 0)),
            total_credit=Decimal(str(r.total_credit or 0)),
        )
        for r in rows_raw
        if r.account_id in accts
    ]
    rows.sort(key=lambda r: r.code)

    return TrialBalanceReport(
        as_of=as_of,
        tenant_id=tenant_id,
        rows=rows,
        generated_at=datetime.now(tz=UTC),
    )


async def general_ledger(
    db: AsyncSession,
    *,
    tenant_id: str,
    account_id: str,
    from_date: date,
    to_date: date,
) -> GLReport:
    """Return GL detail for one account over a date range."""
    from_dt = datetime.combine(from_date, datetime.min.time()).replace(tzinfo=UTC)
    to_dt = datetime.combine(to_date, datetime.max.time()).replace(tzinfo=UTC)

    # Load account
    acct_result = await db.execute(
        select(Account).where(Account.id == account_id, Account.tenant_id == tenant_id)
    )
    acct = acct_result.scalar_one_or_none()
    if not acct:
        raise ValueError(f"Account {account_id} not found")

    # Opening balance = sum of all posted before from_date
    open_result = await db.execute(
        select(
            func.coalesce(func.sum(JournalLine.functional_debit), 0).label("d"),
            func.coalesce(func.sum(JournalLine.functional_credit), 0).label("c"),
        )
        .join(JournalEntry, JournalLine.journal_entry_id == JournalEntry.id)
        .where(
            JournalLine.account_id == account_id,
            JournalLine.tenant_id == tenant_id,
            JournalEntry.status == "posted",
            JournalEntry.date < from_dt,
        )
    )
    open_row = open_result.one()
    if acct.normal_balance == "debit":
        opening_balance = Decimal(str(open_row.d)) - Decimal(str(open_row.c))
    else:
        opening_balance = Decimal(str(open_row.c)) - Decimal(str(open_row.d))

    # Lines in range
    lines_result = await db.execute(
        select(JournalLine, JournalEntry)
        .join(JournalEntry, JournalLine.journal_entry_id == JournalEntry.id)
        .where(
            JournalLine.account_id == account_id,
            JournalLine.tenant_id == tenant_id,
            JournalEntry.status == "posted",
            JournalEntry.date >= from_dt,
            JournalEntry.date <= to_dt,
        )
        .order_by(JournalEntry.date, JournalEntry.number)
    )
    rows = lines_result.all()

    gl_lines = []
    running = opening_balance
    for jl, je in rows:
        debit = Decimal(str(jl.functional_debit))
        credit = Decimal(str(jl.functional_credit))
        if acct.normal_balance == "debit":
            running += debit - credit
        else:
            running += credit - debit
        gl_lines.append(GLLine(
            date=je.date.date() if hasattr(je.date, "date") else je.date,  # type: ignore[union-attr]
            journal_number=je.number,
            journal_id=je.id,
            description=jl.description or je.description,
            debit=debit,
            credit=credit,
            running_balance=running,
        ))

    return GLReport(
        account_id=account_id,
        account_code=acct.code,
        account_name=acct.name,
        normal_balance=acct.normal_balance,
        from_date=from_date,
        to_date=to_date,
        opening_balance=opening_balance,
        lines=gl_lines,
        closing_balance=running,
    )
