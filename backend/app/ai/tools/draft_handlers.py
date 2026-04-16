"""Draft and mutation tool handlers."""
from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infra.models import Account, Period

# In-memory draft store (per-process, cleared on restart)
_drafts: dict[str, dict[str, Any]] = {}


async def handle_draft_journal_entry(
    db: AsyncSession,
    tenant_id: str,
    input_: dict[str, Any],
) -> dict[str, Any]:
    """Validate and store a proposed journal entry draft. Does NOT write to DB."""
    lines = input_["lines"]

    # Validate balance
    total_dr = sum(Decimal(str(ln["debit"])) for ln in lines)
    total_cr = sum(Decimal(str(ln["credit"])) for ln in lines)
    if total_dr != total_cr:
        return {
            "error": f"Journal entry is not balanced: debits={total_dr} credits={total_cr}",
            "confirmation_required": False,
        }

    # Look up account names for display
    enriched_lines = []
    for ln in lines:
        acct_result = await db.execute(
            select(Account).where(
                Account.tenant_id == tenant_id,
                Account.code == ln["account_code"],
            )
        )
        acct = acct_result.scalar_one_or_none()
        enriched_lines.append(
            {
                "account_code": ln["account_code"],
                "account_name": acct.name if acct else "Unknown",
                "description": ln.get("description", ""),
                "debit": str(Decimal(str(ln["debit"]))),
                "credit": str(Decimal(str(ln["credit"]))),
            }
        )

    draft_id = str(uuid.uuid4())
    draft = {
        "draft_id": draft_id,
        "tenant_id": tenant_id,
        "date": input_["date"],
        "period_name": input_.get("period_name"),
        "description": input_["description"],
        "lines": enriched_lines,
        "total_debit": str(total_dr),
    }
    _drafts[draft_id] = draft

    return {
        "confirmation_required": True,
        "draft_id": draft_id,
        "proposed_entry": draft,
        "message": "Draft created. Show this to the user and ask for confirmation before posting.",
    }


async def handle_post_journal_entry(
    db: AsyncSession,
    tenant_id: str,
    input_: dict[str, Any],
    *,
    confirmed: bool = False,
) -> dict[str, Any]:
    """Post a drafted journal entry. Only executes if confirmed=True."""
    if not confirmed:
        return {
            "confirmation_required": True,
            "message": "User confirmation required before posting.",
        }

    draft_id = input_["draft_id"]
    draft = _drafts.get(draft_id)
    if not draft:
        return {"error": f"Draft {draft_id} not found or expired."}
    if draft["tenant_id"] != tenant_id:
        return {"error": "Draft does not belong to this tenant."}

    # Import here to avoid circular imports
    from app.domain.ledger.journal import JournalLineInput
    from app.services.journals import create_draft as svc_create
    from app.services.journals import post_journal as svc_post

    # Look up account IDs and build line inputs
    lines_input = []
    for ln in draft["lines"]:
        acct_result = await db.execute(
            select(Account).where(
                Account.tenant_id == tenant_id,
                Account.code == ln["account_code"],
            )
        )
        acct = acct_result.scalar_one_or_none()
        if not acct:
            return {"error": f"Account {ln['account_code']} not found"}
        dr = Decimal(ln["debit"])
        cr = Decimal(ln["credit"])
        lines_input.append(
            JournalLineInput(
                account_id=acct.id,
                debit=dr,
                credit=cr,
                currency="USD",
                fx_rate=Decimal("1"),
                functional_debit=dr,
                functional_credit=cr,
                description=ln.get("description") or "",
            )
        )

    # Find the most recent open period
    period_result = await db.execute(
        select(Period)
        .where(
            Period.tenant_id == tenant_id,
            Period.status == "open",
        )
        .order_by(Period.start_date.desc())
        .limit(1)
    )
    period = period_result.scalar_one_or_none()
    if not period:
        return {"error": "No open period found"}

    from datetime import date as date_type

    je_date = date_type.fromisoformat(draft["date"])
    system_actor_id = str(uuid.uuid4())  # ephemeral system actor for AI-initiated posts

    je = await svc_create(
        db,
        tenant_id=tenant_id,
        date_=je_date,
        period_id=period.id,
        description=draft["description"],
        lines=lines_input,
        source_type="ai_draft",
        actor_id=system_actor_id,
    )

    posted = await svc_post(
        db,
        journal_id=je.id,
        tenant_id=tenant_id,
        actor_id=system_actor_id,
    )

    del _drafts[draft_id]
    return {
        "success": True,
        "journal_number": posted.number,
        "message": f"Journal entry {posted.number} posted successfully.",
    }


DRAFT_HANDLERS: dict[str, Any] = {
    "draft_journal_entry": handle_draft_journal_entry,
    "post_journal_entry": handle_post_journal_entry,
}
