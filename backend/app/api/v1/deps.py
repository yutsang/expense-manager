"""FastAPI shared dependencies for v1 API."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import AsyncSessionLocal
from app.core.tenant import set_rls_tenant


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield a DB session with RLS tenant set (if X-Tenant-ID header present)."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def get_tenant_id(
    x_tenant_id: Annotated[str | None, Header(alias="X-Tenant-ID")] = None,
) -> str:
    """Extract tenant_id from X-Tenant-ID header. 401 if missing."""
    if not x_tenant_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-Tenant-ID header is required",
        )
    return x_tenant_id


async def get_db_with_rls(
    db: Annotated[AsyncSession, Depends(get_db)],
    tenant_id: Annotated[str, Depends(get_tenant_id)],
) -> AsyncGenerator[AsyncSession, None]:
    """Yield a DB session with RLS set for the tenant."""
    await set_rls_tenant(db, tenant_id)
    yield db


# Typed aliases for cleaner route signatures
DbSession = Annotated[AsyncSession, Depends(get_db_with_rls)]
TenantId = Annotated[str, Depends(get_tenant_id)]


# Actor — Phase 0 auth not yet wired; use X-Actor-ID header as stub
async def get_actor_id(
    x_actor_id: Annotated[str | None, Header(alias="X-Actor-ID")] = None,
) -> str | None:
    return x_actor_id


ActorId = Annotated[str | None, Depends(get_actor_id)]
