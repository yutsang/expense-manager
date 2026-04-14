"""Feature flag service.

Checks: per-tenant override first, then global default, then Settings fallback.
All flag names are defined as constants here — no magic strings elsewhere.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infra.models import FeatureFlag, FeatureFlagOverride


# ── Flag names (add here, never inline strings in call sites) ────────────────

class Flag:
    AI_ENABLED = "ai_enabled"
    BANK_FEEDS_ENABLED = "bank_feeds_enabled"
    MULTI_CURRENCY = "multi_currency"
    WEBAUTHN_ENABLED = "webauthn_enabled"
    MOBILE_SYNC = "mobile_sync"


# ── Service ───────────────────────────────────────────────────────────────────

async def is_enabled(
    db: AsyncSession,
    flag: str,
    tenant_id: str | None = None,
) -> bool:
    """Return whether the feature flag is enabled for the given tenant.

    Priority: per-tenant override > global DB value > Settings default (False).
    """
    # 1. Check per-tenant override
    if tenant_id:
        result = await db.execute(
            select(FeatureFlagOverride).where(
                FeatureFlagOverride.flag == flag,
                FeatureFlagOverride.tenant_id == tenant_id,
            )
        )
        override = result.scalar_one_or_none()
        if override is not None:
            return override.enabled

    # 2. Check global flag
    result = await db.execute(
        select(FeatureFlag).where(FeatureFlag.flag == flag)
    )
    global_flag = result.scalar_one_or_none()
    if global_flag is not None:
        return global_flag.enabled_global

    # 3. Settings-level default (for flags set via env var)
    from app.core.config import get_settings
    settings = get_settings()
    settings_map = {
        Flag.AI_ENABLED: settings.feature_flag_ai_enabled,
    }
    return settings_map.get(flag, False)


async def set_global(db: AsyncSession, flag: str, *, enabled: bool) -> None:
    """Set a global flag value (upsert)."""
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    stmt = pg_insert(FeatureFlag).values(flag=flag, enabled_global=enabled)
    stmt = stmt.on_conflict_do_update(
        index_elements=["flag"],
        set_={"enabled_global": enabled},
    )
    await db.execute(stmt)


async def set_tenant_override(
    db: AsyncSession, flag: str, tenant_id: str, *, enabled: bool
) -> None:
    """Set a per-tenant override (upsert)."""
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    stmt = pg_insert(FeatureFlagOverride).values(
        flag=flag, tenant_id=tenant_id, enabled=enabled
    )
    stmt = stmt.on_conflict_do_update(
        constraint="uq_flag_overrides_flag_tenant",
        set_={"enabled": enabled},
    )
    await db.execute(stmt)
