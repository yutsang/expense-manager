"""Journal entry service — create, post, void.

Invariants enforced at three layers (CLAUDE.md §2.1):
  1. JournalLineInput dataclass (__post_init__)
  2. validate_balance() in domain/ledger/journal.py
  3. Postgres trigger trg_check_journal_balance on status→posted
"""
from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.emitter import emit
from app.core.logging import get_logger
from app.domain.ledger.journal import (
    JournalBalanceError,
    JournalLineInput,
    JournalStatusError,
    validate_balance,
)
from app.infra.models import JournalEntry, JournalLine
from app.services.periods import assert_can_post

log = get_logger(__name__)


class JournalNotFoundError(ValueError):
    pass


async def _next_number(db: AsyncSession, tenant_id: str, year: int) -> str:
    result = await db.execute(
        text("SELECT next_je_number(:tid, :year)"),
        {"tid": tenant_id, "year": year},
    )
    return str(result.scalar())


async def create_draft(
    db: AsyncSession,
    *,
    tenant_id: str,
    date_: date,
    period_id: str,
    description: str,
    lines: list[JournalLineInput],
    source_type: str = "manual",
    source_id: str | None = None,
    actor_id: str | None = None,
) -> JournalEntry:
    """Create a draft journal entry. Does NOT post; lines are validated for structure."""
    if not lines:
        raise JournalBalanceError("Cannot create a journal with no lines")

    # Validate line structure
    for ln in lines:
        if ln.debit < Decimal("0") or ln.credit < Decimal("0"):
            raise JournalBalanceError("Line amounts must be non-negative")

    now = datetime.now(tz=UTC)
    je_id = str(uuid.uuid4())
    total_d = sum(ln.functional_debit for ln in lines)
    total_c = sum(ln.functional_credit for ln in lines)

    je = JournalEntry(
        id=je_id,
        tenant_id=tenant_id,
        number=f"DRAFT-{je_id[:8]}",  # real number assigned on post
        date=datetime.combine(date_, datetime.min.time()).replace(tzinfo=UTC),
        period_id=period_id,
        description=description,
        source_type=source_type,
        source_id=source_id,
        status="draft",
        total_debit=total_d,
        total_credit=total_c,
        created_at=now,
        updated_at=now,
        created_by=actor_id,
        updated_by=actor_id,
    )
    db.add(je)
    await db.flush()

    for i, ln in enumerate(lines, start=1):
        jl = JournalLine(
            id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            journal_entry_id=je_id,
            line_no=i,
            account_id=ln.account_id,
            contact_id=ln.contact_id,
            description=ln.description or None,
            debit=ln.debit,
            credit=ln.credit,
            currency=ln.currency,
            fx_rate=ln.fx_rate,
            functional_debit=ln.functional_debit,
            functional_credit=ln.functional_credit,
        )
        db.add(jl)

    await db.flush()
    await emit(
        db,
        action="journal.draft",
        entity_type="journal_entry",
        entity_id=je_id,
        actor_type="user" if actor_id else "system",
        actor_id=actor_id,
        tenant_id=tenant_id,
        after={"description": description, "lines": len(lines)},
    )
    return je


async def post_journal(
    db: AsyncSession,
    *,
    journal_id: str,
    tenant_id: str,
    actor_id: str,
    admin_override: bool = False,
) -> JournalEntry:
    """Post a draft journal entry. Validates balance and period status."""
    je = await _get_je(db, journal_id=journal_id, tenant_id=tenant_id)
    if je.status != "draft":
        raise JournalStatusError(f"Only draft journals can be posted (current: {je.status})")

    # Validate period is open (or soft-closed + admin override)
    await assert_can_post(
        db, period_id=je.period_id, tenant_id=tenant_id, admin_override=admin_override
    )

    # Load and validate lines
    lines_result = await db.execute(
        select(JournalLine).where(JournalLine.journal_entry_id == journal_id)
    )
    db_lines = list(lines_result.scalars().all())
    domain_lines = [
        JournalLineInput(
            account_id=ln.account_id,
            debit=Decimal(str(ln.debit)),
            credit=Decimal(str(ln.credit)),
            currency=ln.currency,
            functional_debit=Decimal(str(ln.functional_debit)),
            functional_credit=Decimal(str(ln.functional_credit)),
        )
        for ln in db_lines
    ]
    validate_balance(domain_lines)  # Layer 2 check

    now = datetime.now(tz=UTC)
    number = await _next_number(db, tenant_id, je.date.year)  # type: ignore[attr-defined]
    before = {"status": je.status, "number": je.number}

    je.status = "posted"
    je.number = number
    je.posted_at = now
    je.posted_by = actor_id
    je.updated_at = now
    je.updated_by = actor_id
    je.version += 1
    # DB trigger (layer 3) fires here when SQLAlchemy flushes
    await db.flush()

    await emit(
        db,
        action="journal.post",
        entity_type="journal_entry",
        entity_id=journal_id,
        actor_type="user",
        actor_id=actor_id,
        tenant_id=tenant_id,
        before=before,
        after={"status": "posted", "number": number},
    )
    log.info("journal_posted", number=number, tenant_id=tenant_id)
    return je


async def void_journal(
    db: AsyncSession,
    *,
    journal_id: str,
    tenant_id: str,
    actor_id: str,
    reason: str = "",
) -> tuple[JournalEntry, JournalEntry]:
    """Void a posted journal. Creates a reversal entry. Returns (original, reversal)."""
    original = await _get_je(db, journal_id=journal_id, tenant_id=tenant_id)
    if original.status != "posted":
        raise JournalStatusError(f"Only posted journals can be voided (current: {original.status})")

    # Load original lines
    lines_result = await db.execute(
        select(JournalLine).where(JournalLine.journal_entry_id == journal_id)
    )
    orig_lines = list(lines_result.scalars().all())

    # Build reversal lines (flip debit/credit)
    reversal_inputs = [
        JournalLineInput(
            account_id=ln.account_id,
            debit=Decimal(str(ln.credit)),
            credit=Decimal(str(ln.debit)),
            currency=ln.currency,
            functional_debit=Decimal(str(ln.functional_credit)),
            functional_credit=Decimal(str(ln.functional_debit)),
            description=f"VOID: {ln.description or ''}",
        )
        for ln in orig_lines
    ]

    reversal = await create_draft(
        db,
        tenant_id=tenant_id,
        date_=original.date.date() if hasattr(original.date, "date") else date.today(),  # type: ignore[union-attr]
        period_id=original.period_id,
        description=f"VOID of {original.number}: {reason}",
        lines=reversal_inputs,
        source_type="manual",
        actor_id=actor_id,
    )
    reversal.void_of = journal_id

    # Post reversal
    reversal = await post_journal(
        db, journal_id=reversal.id, tenant_id=tenant_id, actor_id=actor_id
    )

    # Mark original as void
    now = datetime.now(tz=UTC)
    original.status = "void"
    original.updated_at = now
    original.updated_by = actor_id
    original.version += 1
    await db.flush()

    await emit(
        db,
        action="journal.void",
        entity_type="journal_entry",
        entity_id=journal_id,
        actor_type="user",
        actor_id=actor_id,
        tenant_id=tenant_id,
        before={"status": "posted"},
        after={"status": "void", "reversal_id": reversal.id},
    )
    log.info("journal_voided", number=original.number, reversal=reversal.number)
    return original, reversal


async def get_journal(
    db: AsyncSession, *, journal_id: str, tenant_id: str
) -> JournalEntry:
    return await _get_je(db, journal_id=journal_id, tenant_id=tenant_id)


async def list_journals(
    db: AsyncSession,
    *,
    tenant_id: str,
    status: str | None = None,
    period_id: str | None = None,
    limit: int = 50,
    cursor: str | None = None,
) -> list[JournalEntry]:
    q = (
        select(JournalEntry)
        .where(JournalEntry.tenant_id == tenant_id)
        .order_by(JournalEntry.date.desc(), JournalEntry.number.desc())
        .limit(limit)
    )
    if status:
        q = q.where(JournalEntry.status == status)
    if period_id:
        q = q.where(JournalEntry.period_id == period_id)
    if cursor:
        q = q.where(JournalEntry.id < cursor)
    result = await db.execute(q)
    return list(result.scalars().all())


async def _get_je(
    db: AsyncSession, *, journal_id: str, tenant_id: str
) -> JournalEntry:
    result = await db.execute(
        select(JournalEntry).where(
            JournalEntry.id == journal_id, JournalEntry.tenant_id == tenant_id
        )
    )
    je = result.scalar_one_or_none()
    if not je:
        raise JournalNotFoundError(f"Journal {journal_id} not found")
    return je
