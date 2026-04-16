"""Audit log emitter — writes append-only, hash-chained audit_events.

Rules (from CLAUDE.md §10):
- Writing the audit event is part of the *same transaction* as the business change.
- If the audit write fails, the business write rolls back.
- Hash chain: prev_hash = hash of tenant's last event; hash = sha256(prev_hash || canonical_json)
- Never write audit events from the API layer — go through service methods.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger

log = get_logger(__name__)

_GENESIS_HASH = b"\x00" * 32  # sentinel prev_hash for the first event per tenant


def _canonical_json(data: dict[str, Any]) -> bytes:
    """Deterministic JSON serialization for hashing."""
    return json.dumps(data, sort_keys=True, separators=(",", ":"), default=str).encode()


def _compute_hash(prev_hash: bytes, event_data: dict[str, Any]) -> bytes:
    h = hashlib.sha256()
    h.update(prev_hash)
    h.update(_canonical_json(event_data))
    return h.digest()


async def _get_prev_hash(session: AsyncSession, tenant_id: str | None) -> bytes:
    """Fetch the hash of the tenant's most recent audit event."""
    from sqlalchemy import text

    result = await session.execute(
        text(
            "SELECT hash FROM audit_events "
            "WHERE tenant_id = :tid OR (tenant_id IS NULL AND :tid IS NULL) "
            "ORDER BY occurred_at DESC, id DESC LIMIT 1"
        ),
        {"tid": tenant_id},
    )
    row = result.first()
    return bytes(row[0]) if row else _GENESIS_HASH


async def emit(
    session: AsyncSession,
    *,
    action: str,
    entity_type: str,
    entity_id: str | uuid.UUID | None = None,
    actor_type: str = "system",
    actor_id: str | uuid.UUID | None = None,
    session_id: str | uuid.UUID | None = None,
    tenant_id: str | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> str:
    """Emit one audit event inside the current transaction. Returns the new event id."""
    from sqlalchemy import insert

    event_id = str(uuid.uuid4())
    occurred_at = datetime.now(tz=UTC)

    prev_hash = await _get_prev_hash(session, tenant_id)

    event_data: dict[str, Any] = {
        "id": event_id,
        "tenant_id": tenant_id,
        "occurred_at": occurred_at.isoformat(),
        "actor_type": actor_type,
        "actor_id": str(actor_id) if actor_id else None,
        "action": action,
        "entity_type": entity_type,
        "entity_id": str(entity_id) if entity_id else None,
    }
    event_hash = _compute_hash(prev_hash, event_data)

    from app.infra import models  # avoid circular import

    await session.execute(
        insert(models.AuditEvent).values(
            id=event_id,
            tenant_id=tenant_id,
            occurred_at=occurred_at,
            actor_type=actor_type,
            actor_id=str(actor_id) if actor_id else None,
            session_id=str(session_id) if session_id else None,
            ip=ip,
            user_agent=user_agent,
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id) if entity_id else None,
            before_state=before,
            after_state=after,
            metadata_=metadata or {},
            prev_hash=prev_hash,
            hash=event_hash,
        )
    )
    log.debug(
        "audit_event_emitted", action=action, entity_type=entity_type, entity_id=str(entity_id)
    )
    return event_id
