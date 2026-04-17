"""Global search service — cross-entity search (Issue #39).

Searches across contacts, invoices, bills, and journal entries
using ILIKE for fast fuzzy matching. Results are combined and
returned as a flat list with entity type annotations.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.infra.models import Bill, Contact, Invoice, JournalEntry

log = get_logger(__name__)

_MIN_QUERY_LENGTH = 2


class SearchQueryTooShortError(ValueError):
    pass


async def global_search(
    db: AsyncSession,
    *,
    tenant_id: str,
    query: str,
    limit: int = 10,
) -> list[dict]:
    """Search across contacts, invoices, bills, and journals.

    Returns a flat list of result dicts, each containing:
      entity_type, entity_id, title, subtitle, url

    Raises SearchQueryTooShortError if query is less than 2 characters.
    """
    if len(query.strip()) < _MIN_QUERY_LENGTH:
        raise SearchQueryTooShortError(
            f"Search query must be at least {_MIN_QUERY_LENGTH} characters"
        )

    pattern = f"%{query.strip()}%"
    per_entity_limit = max(limit // 4, 3)  # distribute limit across entities
    results: list[dict] = []

    # ── Search Contacts ──────────────────────────────────────────────────
    contact_result = await db.execute(
        select(Contact)
        .where(
            Contact.tenant_id == tenant_id,
            Contact.name.ilike(pattern),
        )
        .limit(per_entity_limit)
    )
    for c in contact_result.scalars().all():
        results.append(
            {
                "entity_type": "contact",
                "entity_id": c.id,
                "title": c.name,
                "subtitle": c.contact_type,
                "url": f"/contacts/{c.id}",
            }
        )

    # ── Search Invoices ──────────────────────────────────────────────────
    invoice_result = await db.execute(
        select(Invoice)
        .where(
            Invoice.tenant_id == tenant_id,
            Invoice.number.ilike(pattern),
        )
        .limit(per_entity_limit)
    )
    for inv in invoice_result.scalars().all():
        results.append(
            {
                "entity_type": "invoice",
                "entity_id": inv.id,
                "title": inv.number,
                "subtitle": f"{inv.status} | {inv.currency} {inv.total} | {inv.issue_date}",
                "url": f"/invoices/{inv.id}",
            }
        )

    # ── Search Bills ─────────────────────────────────────────────────────
    bill_result = await db.execute(
        select(Bill)
        .where(
            Bill.tenant_id == tenant_id,
            Bill.number.ilike(pattern),
        )
        .limit(per_entity_limit)
    )
    for b in bill_result.scalars().all():
        results.append(
            {
                "entity_type": "bill",
                "entity_id": b.id,
                "title": b.number,
                "subtitle": f"{b.status} | {b.currency} {b.total} | {b.issue_date}",
                "url": f"/bills/{b.id}",
            }
        )

    # ── Search Journal Entries ───────────────────────────────────────────
    journal_result = await db.execute(
        select(JournalEntry)
        .where(
            JournalEntry.tenant_id == tenant_id,
            JournalEntry.number.ilike(pattern),
        )
        .limit(per_entity_limit)
    )
    for je in journal_result.scalars().all():
        results.append(
            {
                "entity_type": "journal_entry",
                "entity_id": je.id,
                "title": je.number,
                "subtitle": je.description,
                "url": f"/journals/{je.id}",
            }
        )

    # Trim to limit
    return results[:limit]
