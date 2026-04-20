"""Draft and mutation tool handlers.

Drafts are persisted in the ``ai_drafts`` table (migration 0049) so they
survive process restarts and multi-worker deployments. Each draft has a
24-hour expiry; a retention worker can purge stale rows.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infra.models import Account, AiDraft, Period

DRAFT_TTL = timedelta(hours=24)


def _now() -> datetime:
    return datetime.now(tz=UTC)


async def _store_draft(
    db: AsyncSession,
    *,
    tenant_id: str,
    tool_name: str,
    payload: dict[str, Any],
    conversation_id: str | None = None,
    created_by: str | None = None,
) -> AiDraft:
    draft = AiDraft(
        id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        tool_name=tool_name,
        payload=payload,
        expires_at=_now() + DRAFT_TTL,
        created_by=created_by,
    )
    db.add(draft)
    await db.flush()
    return draft


async def _load_active_draft(
    db: AsyncSession,
    *,
    draft_id: str,
    tenant_id: str,
) -> AiDraft | None:
    """Return the draft if it exists, belongs to the tenant, is not yet confirmed, and not expired."""
    result = await db.execute(
        select(AiDraft).where(
            AiDraft.id == draft_id,
            AiDraft.tenant_id == tenant_id,
        )
    )
    draft = result.scalar_one_or_none()
    if not draft:
        return None
    if draft.confirmed_at is not None:
        return None
    if draft.expires_at < _now():
        return None
    return draft


async def handle_draft_journal_entry(
    db: AsyncSession,
    tenant_id: str,
    input_: dict[str, Any],
) -> dict[str, Any]:
    """Validate and store a proposed journal entry draft. Does NOT write to the GL."""
    lines = input_["lines"]

    total_dr = sum(Decimal(str(ln["debit"])) for ln in lines)
    total_cr = sum(Decimal(str(ln["credit"])) for ln in lines)
    if total_dr != total_cr:
        return {
            "error": f"Journal entry is not balanced: debits={total_dr} credits={total_cr}",
            "confirmation_required": False,
        }

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

    payload = {
        "date": input_["date"],
        "period_name": input_.get("period_name"),
        "description": input_["description"],
        "lines": enriched_lines,
        "total_debit": str(total_dr),
    }
    draft = await _store_draft(
        db, tenant_id=tenant_id, tool_name="draft_journal_entry", payload=payload
    )

    return {
        "confirmation_required": True,
        "draft_id": draft.id,
        "proposed_entry": {"draft_id": draft.id, **payload},
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
    draft = await _load_active_draft(db, draft_id=draft_id, tenant_id=tenant_id)
    if not draft:
        return {"error": f"Draft {draft_id} not found, already posted, or expired."}

    payload = draft.payload

    from app.domain.ledger.journal import JournalLineInput
    from app.services.journals import create_draft as svc_create
    from app.services.journals import post_journal as svc_post

    lines_input = []
    for ln in payload["lines"]:
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

    je_date = date_type.fromisoformat(payload["date"])
    system_actor_id = str(uuid.uuid4())

    je = await svc_create(
        db,
        tenant_id=tenant_id,
        date_=je_date,
        period_id=period.id,
        description=payload["description"],
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

    draft.confirmed_at = _now()
    draft.confirmed_by = system_actor_id
    await db.flush()

    return {
        "success": True,
        "journal_number": posted.number,
        "message": f"Journal entry {posted.number} posted successfully.",
    }


DRAFT_HANDLERS: dict[str, Any] = {
    "draft_journal_entry": handle_draft_journal_entry,
    "post_journal_entry": handle_post_journal_entry,
}
