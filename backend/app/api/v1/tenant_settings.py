"""Tenant settings API — GET and PATCH org-level settings."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.api.v1.deps import ActorId, DbSession, TenantId
from app.api.v1.schemas import TenantSettingsResponse, TenantSettingsUpdate
from app.services.tenant_settings import TenantNotFoundError, get_settings, update_settings

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("", response_model=TenantSettingsResponse)
async def get_tenant_settings(
    db: DbSession,
    tenant_id: TenantId,
) -> TenantSettingsResponse:
    """Return current tenant settings."""
    try:
        data = await get_settings(db, tenant_id)
    except TenantNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    return TenantSettingsResponse(**data)


@router.patch("", response_model=TenantSettingsResponse)
async def patch_tenant_settings(
    body: TenantSettingsUpdate,
    db: DbSession,
    tenant_id: TenantId,
    actor_id: ActorId,
) -> TenantSettingsResponse:
    """Partially update tenant settings (merge)."""
    # Only include fields that were explicitly set
    update_data = body.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No fields to update",
        )
    try:
        result = await update_settings(db, tenant_id, actor_id, update_data)
    except TenantNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    return TenantSettingsResponse(**result)
