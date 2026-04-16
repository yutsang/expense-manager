"""Read tool handlers — pure DB reads, no side effects.

These are called by the AI assistant when Claude uses a read tool.
Each handler receives the parsed tool input dict and a DB session,
and returns a JSON-serialisable dict.

All handlers are idempotent and safe to call at any time.
"""
from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infra.models import Account, JournalEntry, JournalLine, Period
from app.services.reports import trial_balance


async def handle_get_account_balance(
    db: AsyncSession,
    tenant_id: str,
    input_: dict[str, Any],
) -> dict[str, Any]:
    """Return balance for a single account by code."""
    code = input_["account_code"]
    as_of = date.fromisoformat(input_["as_of_date"]) if "as_of_date" in input_ else date.today()

    # Look up account
    acct_result = await db.execute(
        select(Account).where(Account.tenant_id == tenant_id, Account.code == code)
    )
    acct = acct_result.scalar_one_or_none()
    if not acct:
        return {"error": f"Account with code '{code}' not found"}

    as_of_dt = datetime.combine(as_of, datetime.max.time()).replace(tzinfo=UTC)

    sums = await db.execute(
        select(
            func.coalesce(func.sum(JournalLine.functional_debit), 0).label("d"),
            func.coalesce(func.sum(JournalLine.functional_credit), 0).label("c"),
        )
        .join(JournalEntry, JournalLine.journal_entry_id == JournalEntry.id)
        .where(
            JournalLine.account_id == acct.id,
            JournalLine.tenant_id == tenant_id,
            JournalEntry.status == "posted",
            JournalEntry.date <= as_of_dt,
        )
    )
    row = sums.one()
    d, c = Decimal(str(row.d)), Decimal(str(row.c))
    balance = (d - c) if acct.normal_balance == "debit" else (c - d)

    return {
        "account_code": acct.code,
        "account_name": acct.name,
        "type": acct.type,
        "normal_balance": acct.normal_balance,
        "as_of_date": str(as_of),
        "balance": str(balance),
        "total_debit": str(d),
        "total_credit": str(c),
    }


async def handle_list_journal_entries(
    db: AsyncSession,
    tenant_id: str,
    input_: dict[str, Any],
) -> dict[str, Any]:
    """List recent journal entries with optional filters."""
    limit = min(int(input_.get("limit", 10)), 50)
    status_filter = input_.get("status")
    period_name = input_.get("period_name")

    q = (
        select(JournalEntry)
        .where(JournalEntry.tenant_id == tenant_id)
        .order_by(JournalEntry.date.desc(), JournalEntry.number.desc())
        .limit(limit)
    )
    if status_filter:
        q = q.where(JournalEntry.status == status_filter)
    if period_name:
        # Join to Period by name
        period_result = await db.execute(
            select(Period).where(Period.tenant_id == tenant_id, Period.name == period_name)
        )
        period = period_result.scalar_one_or_none()
        if not period:
            return {"error": f"Period '{period_name}' not found"}
        q = q.where(JournalEntry.period_id == period.id)

    result = await db.execute(q)
    entries = result.scalars().all()

    return {
        "entries": [
            {
                "id": je.id,
                "number": je.number,
                "date": str(je.date.date() if hasattr(je.date, "date") else je.date),
                "description": je.description,
                "status": je.status,
                "total_debit": str(je.total_debit),
                "total_credit": str(je.total_credit),
            }
            for je in entries
        ],
        "count": len(entries),
    }


async def handle_get_period_status(
    db: AsyncSession,
    tenant_id: str,
    input_: dict[str, Any],
) -> dict[str, Any]:
    """Return status for a named period."""
    name = input_["period_name"]
    result = await db.execute(
        select(Period).where(Period.tenant_id == tenant_id, Period.name == name)
    )
    period = result.scalar_one_or_none()
    if not period:
        return {"error": f"Period '{name}' not found"}

    return {
        "name": period.name,
        "status": period.status,
        "start_date": str(period.start_date.date() if hasattr(period.start_date, "date") else period.start_date),
        "end_date": str(period.end_date.date() if hasattr(period.end_date, "date") else period.end_date),
        "can_post": period.status == "open",
        "can_post_with_override": period.status in ("open", "soft_closed"),
    }


async def handle_search_transactions(
    db: AsyncSession,
    tenant_id: str,
    input_: dict[str, Any],
) -> dict[str, Any]:
    """Full-text search across JE and line descriptions."""
    query = input_["query"].strip()
    limit = min(int(input_.get("limit", 10)), 25)
    from_date = date.fromisoformat(input_["from_date"]) if "from_date" in input_ else None
    to_date = date.fromisoformat(input_["to_date"]) if "to_date" in input_ else None

    q = (
        select(JournalEntry)
        .where(
            JournalEntry.tenant_id == tenant_id,
            JournalEntry.status == "posted",
            or_(
                JournalEntry.description.ilike(f"%{query}%"),
            ),
        )
        .order_by(JournalEntry.date.desc())
        .limit(limit)
    )
    if from_date:
        from_dt = datetime.combine(from_date, datetime.min.time()).replace(tzinfo=UTC)
        q = q.where(JournalEntry.date >= from_dt)
    if to_date:
        to_dt = datetime.combine(to_date, datetime.max.time()).replace(tzinfo=UTC)
        q = q.where(JournalEntry.date <= to_dt)

    result = await db.execute(q)
    entries = result.scalars().all()

    return {
        "query": query,
        "matches": [
            {
                "number": je.number,
                "date": str(je.date.date() if hasattr(je.date, "date") else je.date),
                "description": je.description,
                "total_debit": str(je.total_debit),
            }
            for je in entries
        ],
        "count": len(entries),
    }


async def handle_get_trial_balance(
    db: AsyncSession,
    tenant_id: str,
    input_: dict[str, Any],
) -> dict[str, Any]:
    """Return the trial balance as of a given date."""
    as_of = date.fromisoformat(input_["as_of_date"]) if "as_of_date" in input_ else date.today()
    report = await trial_balance(db, tenant_id=tenant_id, as_of=as_of)

    return {
        "as_of_date": str(report.as_of),
        "is_balanced": report.is_balanced,
        "total_debit": str(report.total_debit),
        "total_credit": str(report.total_credit),
        "rows": [
            {
                "code": r.code,
                "name": r.name,
                "type": r.type,
                "balance": str(r.balance),
            }
            for r in report.rows
        ],
    }


# ── Dispatch map ─────────────────────────────────────────────────────────────

HANDLERS = {
    "get_account_balance": handle_get_account_balance,
    "list_journal_entries": handle_list_journal_entries,
    "get_period_status": handle_get_period_status,
    "search_transactions": handle_search_transactions,
    "get_trial_balance": handle_get_trial_balance,
}


async def dispatch(
    db: AsyncSession,
    tenant_id: str,
    tool_name: str,
    tool_input: dict[str, Any],
) -> dict[str, Any]:
    """Route a tool call to the correct handler. Returns error dict if unknown."""
    handler = HANDLERS.get(tool_name)
    if not handler:
        return {"error": f"Unknown tool: {tool_name}"}
    return await handler(db, tenant_id, tool_input)
