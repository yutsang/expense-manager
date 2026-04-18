"""Tenant settings service — get and update org-level settings.

Settings are stored partly on Tenant columns (name, country,
functional_currency, fiscal_year_start_month, tax_rounding_policy) and
partly in the ``settings`` JSONB column (notification_prefs, etc.).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.emitter import emit
from app.core.logging import get_logger
from app.infra.models import Tenant

log = get_logger(__name__)


class TenantNotFoundError(ValueError):
    pass


async def _get_tenant(db: AsyncSession, tenant_id: str) -> Tenant:
    tenant = await db.scalar(select(Tenant).where(Tenant.id == tenant_id))
    if not tenant:
        raise TenantNotFoundError(f"Tenant not found: {tenant_id}")
    return tenant


async def get_settings(db: AsyncSession, tenant_id: str) -> dict[str, Any]:
    """Return the current tenant settings as a flat dictionary."""
    tenant = await _get_tenant(db, tenant_id)
    settings_json: dict[str, Any] = tenant.settings or {}

    return {
        "org_name": tenant.name,
        "country": tenant.country,
        "functional_currency": tenant.functional_currency,
        "fiscal_year_start_month": tenant.fiscal_year_start_month,
        "tax_rounding_policy": tenant.tax_rounding_policy,
        "invoice_approval_threshold": (
            str(tenant.invoice_approval_threshold)
            if tenant.invoice_approval_threshold is not None
            else None
        ),
        "notification_prefs": settings_json.get("notification_prefs", {}),
    }


async def update_settings(
    db: AsyncSession,
    tenant_id: str,
    actor_id: str | None,
    data: dict[str, Any],
) -> dict[str, Any]:
    """Merge *data* into tenant settings. Returns the updated settings dict."""
    tenant = await _get_tenant(db, tenant_id)

    before: dict[str, Any] = {
        "name": tenant.name,
        "country": tenant.country,
        "functional_currency": tenant.functional_currency,
        "fiscal_year_start_month": tenant.fiscal_year_start_month,
        "tax_rounding_policy": tenant.tax_rounding_policy,
    }

    # Apply column-level fields
    if "org_name" in data and data["org_name"] is not None:
        tenant.name = data["org_name"]
    if "country" in data and data["country"] is not None:
        tenant.country = data["country"]
    if "functional_currency" in data and data["functional_currency"] is not None:
        tenant.functional_currency = data["functional_currency"]
    if "fiscal_year_start_month" in data and data["fiscal_year_start_month"] is not None:
        tenant.fiscal_year_start_month = data["fiscal_year_start_month"]
    if "tax_rounding_policy" in data and data["tax_rounding_policy"] is not None:
        tenant.tax_rounding_policy = data["tax_rounding_policy"]
    if "invoice_approval_threshold" in data:
        from decimal import Decimal

        val = data["invoice_approval_threshold"]
        tenant.invoice_approval_threshold = Decimal(val) if val is not None else None

    # Merge JSONB settings
    settings_json: dict[str, Any] = dict(tenant.settings or {})
    if "notification_prefs" in data and data["notification_prefs"] is not None:
        settings_json["notification_prefs"] = data["notification_prefs"]
    tenant.settings = settings_json

    tenant.updated_at = datetime.now(tz=UTC)
    tenant.version += 1

    after: dict[str, Any] = {
        "name": tenant.name,
        "country": tenant.country,
        "functional_currency": tenant.functional_currency,
        "fiscal_year_start_month": tenant.fiscal_year_start_month,
        "tax_rounding_policy": tenant.tax_rounding_policy,
    }

    await db.flush()

    await emit(
        session=db,
        action="tenant_settings.updated",
        entity_type="tenant",
        entity_id=tenant.id,
        actor_type="user",
        actor_id=actor_id,
        tenant_id=tenant_id,
        before=before,
        after=after,
    )
    log.info("tenant_settings.updated", tenant_id=tenant_id)

    return await get_settings(db, tenant_id)
