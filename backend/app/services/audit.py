"""Audit service — chain verification, event listing, sampling, JE testing."""
from __future__ import annotations

import hashlib
import json
import random
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infra.models import AuditChainVerification, AuditEvent, JournalEntry, ReportSnapshot

# ---------------------------------------------------------------------------
# Chain verification
# ---------------------------------------------------------------------------

_GENESIS_HASH = b"\x00" * 32


def _canonical_json(data: dict[str, Any]) -> bytes:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), default=str).encode()


def _compute_hash(prev_hash: bytes, event_data: dict[str, Any]) -> bytes:
    h = hashlib.sha256()
    h.update(prev_hash)
    h.update(_canonical_json(event_data))
    return h.digest()


async def verify_chain(db: AsyncSession, tenant_id: str) -> dict[str, Any]:
    """Walk the entire audit_events chain for a tenant and verify hash continuity.

    Returns {is_valid, chain_length, break_at_event_id, last_event_id, error_message}
    and writes the result to audit_chain_verifications.
    """
    result = await db.execute(
        select(AuditEvent)
        .where(AuditEvent.tenant_id == tenant_id)
        .order_by(AuditEvent.occurred_at.asc(), AuditEvent.id.asc())
    )
    events = list(result.scalars().all())

    is_valid = True
    break_at: str | None = None
    error_msg: str | None = None
    prev_hash = _GENESIS_HASH

    for event in events:
        event_data: dict[str, Any] = {
            "id": event.id,
            "tenant_id": event.tenant_id,
            "occurred_at": event.occurred_at.isoformat() if isinstance(event.occurred_at, datetime) else str(event.occurred_at),
            "actor_type": event.actor_type,
            "actor_id": str(event.actor_id) if event.actor_id else None,
            "action": event.action,
            "entity_type": event.entity_type,
            "entity_id": str(event.entity_id) if event.entity_id else None,
        }
        expected_hash = _compute_hash(prev_hash, event_data)
        stored_hash = bytes(event.hash)

        if stored_hash != expected_hash:
            is_valid = False
            break_at = event.id
            error_msg = f"Hash mismatch at event {event.id}"
            break

        prev_hash = stored_hash

    last_event_id = events[-1].id if events else None

    verification = AuditChainVerification(
        tenant_id=tenant_id,
        verified_at=datetime.now(tz=UTC),
        chain_length=len(events),
        last_event_id=last_event_id,
        is_valid=is_valid,
        break_at_event_id=break_at,
        error_message=error_msg,
    )
    db.add(verification)
    await db.flush()

    return {
        "id": verification.id,
        "is_valid": is_valid,
        "chain_length": len(events),
        "break_at_event_id": break_at,
        "last_event_id": last_event_id,
        "error_message": error_msg,
        "verified_at": verification.verified_at,
    }


async def get_chain_verification_history(
    db: AsyncSession, tenant_id: str, limit: int = 10
) -> list[AuditChainVerification]:
    result = await db.execute(
        select(AuditChainVerification)
        .where(AuditChainVerification.tenant_id == tenant_id)
        .order_by(AuditChainVerification.verified_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Event listing (paginated)
# ---------------------------------------------------------------------------


async def list_audit_events(
    db: AsyncSession,
    tenant_id: str,
    *,
    actor_id: str | None = None,
    action: str | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    from_dt: datetime | None = None,
    to_dt: datetime | None = None,
    limit: int = 50,
    cursor: str | None = None,
) -> tuple[list[AuditEvent], str | None]:
    """Return paginated audit events with optional filters. Cursor is last event id."""
    q = select(AuditEvent).where(AuditEvent.tenant_id == tenant_id)

    if actor_id is not None:
        q = q.where(AuditEvent.actor_id == actor_id)
    if action is not None:
        q = q.where(AuditEvent.action == action)
    if entity_type is not None:
        q = q.where(AuditEvent.entity_type == entity_type)
    if entity_id is not None:
        q = q.where(AuditEvent.entity_id == entity_id)
    if from_dt is not None:
        q = q.where(AuditEvent.occurred_at >= from_dt)
    if to_dt is not None:
        q = q.where(AuditEvent.occurred_at <= to_dt)

    if cursor is not None:
        # Fetch the cursor event to get its occurred_at for keyset pagination
        cursor_result = await db.execute(
            select(AuditEvent.occurred_at).where(AuditEvent.id == cursor)
        )
        cursor_row = cursor_result.first()
        if cursor_row:
            q = q.where(AuditEvent.occurred_at < cursor_row[0])

    q = q.order_by(AuditEvent.occurred_at.desc(), AuditEvent.id.desc()).limit(limit + 1)

    result = await db.execute(q)
    events = list(result.scalars().all())

    next_cursor: str | None = None
    if len(events) > limit:
        events = events[:limit]
        next_cursor = events[-1].id

    return events, next_cursor


async def get_audit_event(db: AsyncSession, event_id: str, tenant_id: str) -> AuditEvent | None:
    result = await db.execute(
        select(AuditEvent)
        .where(AuditEvent.id == event_id, AuditEvent.tenant_id == tenant_id)
    )
    return result.scalar_one_or_none()


# ---------------------------------------------------------------------------
# Journal entry sampling
# ---------------------------------------------------------------------------


async def sample_journal_entries(
    db: AsyncSession,
    tenant_id: str,
    *,
    method: str,
    size: int,
    seed: int,
    from_date: date | None = None,
    to_date: date | None = None,
) -> list[dict[str, Any]]:
    """Return a reproducible sample of posted journal entries.

    method: 'random' | 'monetary_unit' | 'stratified'
    """
    q = (
        select(JournalEntry)
        .where(JournalEntry.tenant_id == tenant_id, JournalEntry.status == "posted")
    )
    if from_date is not None:
        q = q.where(JournalEntry.date >= datetime(from_date.year, from_date.month, from_date.day, tzinfo=UTC))
    if to_date is not None:
        q = q.where(JournalEntry.date <= datetime(to_date.year, to_date.month, to_date.day, 23, 59, 59, tzinfo=UTC))

    result = await db.execute(q.order_by(JournalEntry.date.asc(), JournalEntry.id.asc()))
    all_entries = list(result.scalars().all())

    if not all_entries:
        return []

    rng = random.Random(seed)  # noqa: S311
    effective_size = min(size, len(all_entries))

    if method == "random":
        sampled = rng.sample(all_entries, effective_size)

    elif method == "monetary_unit":
        # Sort by total_debit descending, then systematic interval
        sorted_entries = sorted(all_entries, key=lambda e: float(e.total_debit or 0), reverse=True)
        interval = max(1, len(sorted_entries) // effective_size)
        start = rng.randint(0, interval - 1)
        sampled = sorted_entries[start::interval][:effective_size]

    elif method == "stratified":
        # 3 strata: small (<1000), medium (1000-10000), large (>10000)
        small = [e for e in all_entries if float(e.total_debit or 0) < 1000]
        medium = [e for e in all_entries if 1000 <= float(e.total_debit or 0) <= 10000]
        large = [e for e in all_entries if float(e.total_debit or 0) > 10000]

        # Proportional allocation
        total = len(all_entries)
        n_small = round(effective_size * len(small) / total) if total else 0
        n_large = round(effective_size * len(large) / total) if total else 0
        n_medium = effective_size - n_small - n_large

        sampled = (
            rng.sample(small, min(n_small, len(small)))
            + rng.sample(medium, min(n_medium, len(medium)))
            + rng.sample(large, min(n_large, len(large)))
        )
    else:
        raise ValueError(f"Unknown sampling method: {method!r}. Use 'random', 'monetary_unit', or 'stratified'.")

    return [
        {
            "id": e.id,
            "number": e.number,
            "date": e.date.isoformat() if isinstance(e.date, datetime) else str(e.date),
            "description": e.description,
            "total_debit": str(e.total_debit),
            "total_credit": str(e.total_credit),
            "currency": e.currency,
            "status": e.status,
        }
        for e in sampled
    ]


# ---------------------------------------------------------------------------
# JE testing / analytical queries
# ---------------------------------------------------------------------------


async def get_je_testing_report(
    db: AsyncSession,
    tenant_id: str,
    *,
    from_date: date,
    to_date: date,
) -> dict[str, Any]:
    """Return analytical signals useful for journal entry testing."""
    from_dt = datetime(from_date.year, from_date.month, from_date.day, tzinfo=UTC)
    to_dt = datetime(to_date.year, to_date.month, to_date.day, 23, 59, 59, tzinfo=UTC)

    q_base = (
        select(JournalEntry)
        .where(
            JournalEntry.tenant_id == tenant_id,
            JournalEntry.status == "posted",
            JournalEntry.date >= from_dt,
            JournalEntry.date <= to_dt,
        )
    )

    result = await db.execute(q_base.order_by(JournalEntry.date.asc()))
    entries = list(result.scalars().all())

    # Cutoff entries: within 3 days of month boundary
    cutoff_entries = []
    for e in entries:
        entry_date = e.date if isinstance(e.date, datetime) else datetime.fromisoformat(str(e.date))
        day = entry_date.day
        # last 3 days of month: approximate via day >= 28; first 3: day <= 3
        if day <= 3 or day >= 28:
            cutoff_entries.append(e)

    # Weekend/holiday posts: Saturday (5) or Sunday (6)
    weekend_entries = [
        e for e in entries
        if (e.date if isinstance(e.date, datetime) else datetime.fromisoformat(str(e.date))).weekday() >= 5
    ]

    # Round number entries: total_debit is exact multiple of 100
    round_entries = [
        e for e in entries
        if float(e.total_debit or 0) > 0 and float(e.total_debit or 0) % 100 == 0
    ]

    # Top 20 by total
    large_entries = sorted(entries, key=lambda e: float(e.total_debit or 0), reverse=True)[:20]

    # Reversed same day: void_of is set and void entry date == original entry date
    # Find entries that are voids of another entry posted same day
    void_entries = [e for e in entries if e.void_of is not None]
    reversed_same_day = []
    entry_map = {e.id: e for e in entries}
    for void_e in void_entries:
        original = entry_map.get(void_e.void_of or "")
        if original:
            void_date = void_e.date if isinstance(void_e.date, datetime) else datetime.fromisoformat(str(void_e.date))
            orig_date = original.date if isinstance(original.date, datetime) else datetime.fromisoformat(str(original.date))
            if void_date.date() == orig_date.date():
                reversed_same_day.append(void_e)

    def _entry_dict(e: JournalEntry) -> dict[str, Any]:
        return {
            "id": e.id,
            "number": e.number,
            "date": e.date.isoformat() if isinstance(e.date, datetime) else str(e.date),
            "description": e.description,
            "total_debit": str(e.total_debit),
            "currency": e.currency,
        }

    return {
        "cutoff_entries": [_entry_dict(e) for e in cutoff_entries],
        "weekend_holiday_posts": [_entry_dict(e) for e in weekend_entries],
        "round_number_entries": [_entry_dict(e) for e in round_entries],
        "large_entries": [_entry_dict(e) for e in large_entries],
        "reversed_same_day": [_entry_dict(e) for e in reversed_same_day],
    }


# ---------------------------------------------------------------------------
# Report snapshots
# ---------------------------------------------------------------------------


async def create_report_snapshot(
    db: AsyncSession,
    tenant_id: str,
    *,
    report_type: str,
    params: dict[str, Any],
    data: dict[str, Any],
    created_by: str,
) -> ReportSnapshot:
    """Store an immutable report snapshot with sha256 of the data."""
    data_bytes = json.dumps(data, sort_keys=True, separators=(",", ":"), default=str).encode()
    sha256_hex = hashlib.sha256(data_bytes).hexdigest()

    snapshot = ReportSnapshot(
        tenant_id=tenant_id,
        report_type=report_type,
        params=params,
        generated_at=datetime.now(tz=UTC),
        data=data,
        sha256=sha256_hex,
        created_by=created_by,
    )
    db.add(snapshot)
    await db.flush()
    return snapshot


async def list_report_snapshots(
    db: AsyncSession,
    tenant_id: str,
    limit: int = 50,
    cursor: str | None = None,
) -> tuple[list[ReportSnapshot], str | None]:
    q = select(ReportSnapshot).where(ReportSnapshot.tenant_id == tenant_id)

    if cursor is not None:
        cursor_result = await db.execute(
            select(ReportSnapshot.created_at).where(ReportSnapshot.id == cursor)
        )
        cursor_row = cursor_result.first()
        if cursor_row:
            q = q.where(ReportSnapshot.created_at < cursor_row[0])

    q = q.order_by(ReportSnapshot.created_at.desc()).limit(limit + 1)
    result = await db.execute(q)
    snapshots = list(result.scalars().all())

    next_cursor: str | None = None
    if len(snapshots) > limit:
        snapshots = snapshots[:limit]
        next_cursor = snapshots[-1].id

    return snapshots, next_cursor


async def get_report_snapshot(
    db: AsyncSession, snapshot_id: str, tenant_id: str
) -> ReportSnapshot | None:
    result = await db.execute(
        select(ReportSnapshot)
        .where(ReportSnapshot.id == snapshot_id, ReportSnapshot.tenant_id == tenant_id)
    )
    return result.scalar_one_or_none()
