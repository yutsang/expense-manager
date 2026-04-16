"""Mobile Sync API — device registration, pull, push."""
from __future__ import annotations

from datetime import UTC

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func, select

from app.api.v1.deps import ActorId, DbSession, TenantId
from app.infra.models import SyncDevice
from app.services.sync import (
    SyncDeviceNotFoundError,
    pull_changes,
    push_operations,
    register_device,
    update_push_token,
)

router = APIRouter(prefix="/sync", tags=["sync"])


# ── Request / Response schemas ──────────────────────────────────────────────


class DeviceRegisterRequest(BaseModel):
    platform: str
    app_version: str | None = None
    device_fingerprint: str
    push_token: str | None = None


class DeviceRegisterResponse(BaseModel):
    id: str
    tenant_id: str
    user_id: str
    device_fingerprint: str
    platform: str
    app_version: str | None
    push_token: str | None
    last_seen: str | None

    model_config = {"from_attributes": True}


class PushTokenRequest(BaseModel):
    push_token: str


class PushOpItem(BaseModel):
    client_op_id: str
    entity_type: str
    entity_id: str | None = None
    base_version: int | None = None
    new_state: dict = {}


class PushRequest(BaseModel):
    device_fingerprint: str
    ops: list[PushOpItem]


class SyncStatusResponse(BaseModel):
    server_time: str
    tenant_id: str
    device_count: int


# ── Helpers ──────────────────────────────────────────────────────────────────


def _device_response(device: SyncDevice) -> DeviceRegisterResponse:
    return DeviceRegisterResponse(
        id=device.id,
        tenant_id=device.tenant_id,
        user_id=device.user_id,
        device_fingerprint=device.device_fingerprint,
        platform=device.platform,
        app_version=device.app_version,
        push_token=device.push_token,
        last_seen=device.last_seen.isoformat() if device.last_seen else None,
    )


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.post(
    "/devices",
    response_model=DeviceRegisterResponse,
    status_code=status.HTTP_200_OK,
    summary="Register or update a device",
)
async def register_device_endpoint(
    body: DeviceRegisterRequest,
    db: DbSession,
    tenant_id: TenantId,
    actor_id: ActorId,
) -> DeviceRegisterResponse:
    if not actor_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="X-Actor-ID required")
    if body.platform not in ("ios", "android", "web"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="platform must be one of: ios, android, web",
        )
    device = await register_device(
        db,
        tenant_id=tenant_id,
        user_id=actor_id,
        platform=body.platform,
        app_version=body.app_version,
        device_fingerprint=body.device_fingerprint,
        push_token=body.push_token,
    )
    await db.commit()
    return _device_response(device)


@router.patch(
    "/devices/{fingerprint}/push-token",
    response_model=DeviceRegisterResponse,
    summary="Update push notification token for a device",
)
async def update_push_token_endpoint(
    fingerprint: str,
    body: PushTokenRequest,
    db: DbSession,
    tenant_id: TenantId,
    actor_id: ActorId,
) -> DeviceRegisterResponse:
    if not actor_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="X-Actor-ID required")
    try:
        device = await update_push_token(db, tenant_id=tenant_id, device_fingerprint=fingerprint, push_token=body.push_token)
        await db.commit()
    except SyncDeviceNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return _device_response(device)


@router.get(
    "/pull",
    summary="Pull entity changes since cursor",
)
async def pull_endpoint(
    db: DbSession,
    tenant_id: TenantId,
    cursor: str | None = Query(default=None, description="ISO-8601 timestamp; omit for full sync"),
    limit: int = Query(default=100, ge=1, le=200),
) -> dict:
    return await pull_changes(db, tenant_id, cursor=cursor, limit=limit)


@router.post(
    "/push",
    summary="Push client mutations to the server",
)
async def push_endpoint(
    body: PushRequest,
    db: DbSession,
    tenant_id: TenantId,
    actor_id: ActorId,
) -> dict:
    if not actor_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="X-Actor-ID required")

    # Resolve device_id from fingerprint (optional — proceed even if device not found)
    device = await db.scalar(
        select(SyncDevice).where(
            SyncDevice.tenant_id == tenant_id,
            SyncDevice.device_fingerprint == body.device_fingerprint,
        )
    )
    device_id = device.id if device else None

    ops_dicts = [op.model_dump() for op in body.ops]
    results = await push_operations(
        db,
        tenant_id=tenant_id,
        user_id=actor_id,
        device_id=device_id,
        ops=ops_dicts,
    )
    await db.commit()
    return {"results": results}


@router.get(
    "/status",
    response_model=SyncStatusResponse,
    summary="Sync health / status for the current tenant",
)
async def sync_status_endpoint(
    db: DbSession,
    tenant_id: TenantId,
) -> SyncStatusResponse:
    from datetime import datetime

    now = datetime.now(tz=UTC)
    count_result = await db.execute(
        select(func.count()).select_from(SyncDevice).where(SyncDevice.tenant_id == tenant_id)
    )
    device_count = count_result.scalar() or 0
    return SyncStatusResponse(
        server_time=now.isoformat(),
        tenant_id=tenant_id,
        device_count=device_count,
    )
