"""Builds a tenant-context block injected into every AI conversation.

Cached per tenant for 5 minutes so repeated chats don't re-query.
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# Simple in-process cache: {tenant_id: (built_at_epoch, context_str)}
_CACHE: dict[str, tuple[float, str]] = {}
_TTL_SECONDS = 300  # 5 minutes


async def build_tenant_context(db: AsyncSession, tenant_id: str) -> str:
    """Return a markdown string with chart of accounts, open periods, recent activity.

    Results are cached per tenant for 5 minutes.
    """
    now = time.monotonic()
    cached = _CACHE.get(tenant_id)
    if cached is not None:
        built_at, ctx = cached
        if now - built_at < _TTL_SECONDS:
            return ctx

    ctx = await _build(db, tenant_id)
    _CACHE[tenant_id] = (now, ctx)
    return ctx


async def _build(db: AsyncSession, tenant_id: str) -> str:
    sections: list[str] = []

    # --- Functional currency (from tenant record) ---
    currency_row = await db.execute(
        text("SELECT functional_currency FROM tenants WHERE id = :tid"),
        {"tid": tenant_id},
    )
    row = currency_row.fetchone()
    functional_currency = row.functional_currency if row else "USD"

    sections.append(f"## Functional Currency\n{functional_currency}")

    # --- Top 20 most-used accounts ---
    accts_row = await db.execute(
        text("""
            SELECT
                a.code,
                a.name,
                a.type,
                a.normal_balance,
                COUNT(jl.id) AS line_count
            FROM accounts a
            LEFT JOIN journal_lines jl ON jl.account_id = a.id
            WHERE a.tenant_id = :tid
              AND a.is_active = TRUE
            GROUP BY a.id, a.code, a.name, a.type, a.normal_balance
            ORDER BY line_count DESC, a.code ASC
            LIMIT 20
        """),
        {"tid": tenant_id},
    )
    accts = accts_row.fetchall()

    if accts:
        header = "## Your Chart of Accounts (top 20 most-used)\n| Code | Name | Type | Normal Balance |"
        separator = "|------|------|------|----------------|"
        rows = [f"| {r.code} | {r.name} | {r.type} | {r.normal_balance} |" for r in accts]
        sections.append("\n".join([header, separator] + rows))
    else:
        sections.append("## Your Chart of Accounts\n_No accounts found._")

    # --- Open periods ---
    periods_row = await db.execute(
        text("""
            SELECT name, start_date, end_date
            FROM periods
            WHERE tenant_id = :tid
              AND status = 'open'
            ORDER BY start_date ASC
        """),
        {"tid": tenant_id},
    )
    periods = periods_row.fetchall()

    if periods:
        lines = ["## Open Periods"]
        for p in periods:
            sd = p.start_date.date() if isinstance(p.start_date, datetime) else p.start_date
            ed = p.end_date.date() if isinstance(p.end_date, datetime) else p.end_date
            lines.append(f"- **{p.name}**: {sd} to {ed}")
        sections.append("\n".join(lines))
    else:
        sections.append("## Open Periods\n_No open periods._")

    # --- Recent activity (last 7 days) ---
    cutoff = (datetime.now(tz=timezone.utc) - timedelta(days=7)).date()

    je_row = await db.execute(
        text("""
            SELECT
                COUNT(*) AS je_count,
                COALESCE(SUM(total_debit), 0) AS total_debit
            FROM journal_entries
            WHERE tenant_id = :tid
              AND status = 'posted'
              AND date >= :cutoff
        """),
        {"tid": tenant_id, "cutoff": cutoff},
    )
    je_stats = je_row.fetchone()

    inv_row = await db.execute(
        text("""
            SELECT COUNT(*) AS cnt
            FROM invoices
            WHERE tenant_id = :tid
              AND created_at >= :cutoff
        """),
        {"tid": tenant_id, "cutoff": cutoff},
    )
    inv_count = inv_row.scalar() or 0

    bills_row = await db.execute(
        text("""
            SELECT COUNT(*) AS cnt
            FROM bills
            WHERE tenant_id = :tid
              AND created_at >= :cutoff
        """),
        {"tid": tenant_id, "cutoff": cutoff},
    )
    bills_count = bills_row.scalar() or 0

    je_count = int(je_stats.je_count) if je_stats else 0
    total_debit = str(je_stats.total_debit) if je_stats else "0"

    activity_lines = [
        "## Recent Activity (last 7 days)",
        f"- {je_count} journal entries posted (total debit: {total_debit} {functional_currency})",
        f"- {inv_count} invoices created",
        f"- {bills_count} bills created",
    ]
    sections.append("\n".join(activity_lines))

    return "\n\n".join(sections)


def invalidate_tenant_cache(tenant_id: str) -> None:
    """Remove a tenant's cached context (call after significant data changes)."""
    _CACHE.pop(tenant_id, None)
