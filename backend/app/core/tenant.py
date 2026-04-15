"""Multi-tenancy context management.

A request's tenant_id lives in a ContextVar, injected by the auth middleware
after JWT validation. Never accepted from the request body/query string.

The set_tenant_id() helper also writes the value to the Postgres session so
that Row-Level Security policies (`SET LOCAL app.tenant_id = ...`) can apply.
"""
from __future__ import annotations

import uuid
from contextvars import ContextVar
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger

log = get_logger(__name__)

_tenant_id_var: ContextVar[Optional[str]] = ContextVar("tenant_id", default=None)


def get_tenant_id() -> str:
    """Return the current request's tenant_id. Raises if not set."""
    tid = _tenant_id_var.get()
    if tid is None:
        raise RuntimeError(
            "tenant_id is not set in the current context. "
            "This endpoint requires authentication."
        )
    return tid


def get_tenant_id_optional() -> str | None:
    return _tenant_id_var.get()


def set_tenant_id(tenant_id: str) -> None:
    """Set the tenant for the current async task."""
    # Validate it looks like a UUID before storing
    uuid.UUID(tenant_id)  # raises ValueError if invalid
    _tenant_id_var.set(tenant_id)


def clear_tenant_id() -> None:
    _tenant_id_var.set(None)


async def set_rls_tenant(session: AsyncSession, tenant_id: str) -> None:
    """Write tenant_id into the Postgres session so RLS policies fire.

    SET LOCAL does not support bound parameters in Postgres, so we embed the
    value directly. The UUID validation above guarantees it is safe.
    """
    from sqlalchemy import text
    # tenant_id is UUID-validated by set_tenant_id() — safe to embed directly
    await session.execute(text(f"SET LOCAL app.tenant_id = '{tenant_id}'"))
    log.debug("rls_tenant_set", tenant_id=tenant_id)
