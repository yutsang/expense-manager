"""User management API — list, invite, accept, change role, deactivate.

Gated by the acting user's membership role: only owners/admins can mutate,
everyone authenticated can list (read-only tenant view).
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select

from app.api.v1.deps import ActorId, DbSession, TenantId
from app.core.logging import get_logger
from app.infra.models import Membership
from app.services import users as users_svc

log = get_logger(__name__)

router = APIRouter(prefix="/users", tags=["users"])


class UserRow(BaseModel):
    user_id: str
    email: str
    display_name: str
    role: str
    status: str
    invited_at: datetime | None
    joined_at: datetime | None
    invited_by: str | None
    last_login_at: datetime | None
    membership_id: str


class UserListResponse(BaseModel):
    items: list[UserRow]


class InviteRequest(BaseModel):
    email: EmailStr
    role: str = Field(..., min_length=1, max_length=32)
    display_name: str | None = Field(default=None, max_length=255)


class InviteResponse(BaseModel):
    membership_id: str
    user_id: str
    email: str
    role: str
    status: str
    invite_token: str = Field(
        ...,
        description=(
            "Raw invite token — emailed to the invitee. Shown to the caller "
            "once; never retrievable again."
        ),
    )
    invite_expires_at: datetime | None


class AcceptInviteRequest(BaseModel):
    invite_token: str = Field(..., min_length=10)
    password: str = Field(..., min_length=12, max_length=256)
    display_name: str | None = Field(default=None, max_length=255)


class AcceptInviteResponse(BaseModel):
    user_id: str
    tenant_id: str
    role: str
    status: str


class ChangeRoleRequest(BaseModel):
    role: str = Field(..., min_length=1, max_length=32)


async def _require_admin(db: DbSession, tenant_id: str, actor_id: str | None) -> str:
    """Return the actor_id if they're an owner/admin of the tenant, else 403."""
    if not actor_id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="X-Actor-ID required")
    membership = await db.scalar(
        select(Membership).where(
            Membership.tenant_id == tenant_id,
            Membership.user_id == actor_id,
            Membership.status == "active",
        )
    )
    if membership is None or membership.role not in ("owner", "admin"):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="Only owners or admins can manage users",
        )
    return actor_id


@router.get("", response_model=UserListResponse)
async def list_members(db: DbSession, tenant_id: TenantId) -> UserListResponse:
    rows = await users_svc.list_users(db, tenant_id)
    return UserListResponse(items=[UserRow(**r) for r in rows])


@router.post("/invite", response_model=InviteResponse, status_code=status.HTTP_201_CREATED)
async def invite(
    body: InviteRequest,
    db: DbSession,
    tenant_id: TenantId,
    actor_id: ActorId,
) -> InviteResponse:
    admin_id = await _require_admin(db, tenant_id, actor_id)
    try:
        membership, token = await users_svc.invite_user(
            db,
            tenant_id=tenant_id,
            inviter_user_id=admin_id,
            email=body.email,
            role=body.role,
            display_name=body.display_name,
        )
    except users_svc.InviteError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    await db.commit()
    await db.refresh(membership)

    return InviteResponse(
        membership_id=membership.id,
        user_id=membership.user_id,
        email=body.email,
        role=membership.role,
        status=membership.status,
        invite_token=token,
        invite_expires_at=membership.invite_expires_at,
    )


@router.post("/accept-invite", response_model=AcceptInviteResponse)
async def accept(body: AcceptInviteRequest, db: DbSession) -> AcceptInviteResponse:
    try:
        membership = await users_svc.accept_invite(
            db,
            invite_token=body.invite_token,
            password=body.password,
            display_name=body.display_name,
        )
    except users_svc.InviteError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc))
    await db.commit()

    return AcceptInviteResponse(
        user_id=membership.user_id,
        tenant_id=membership.tenant_id,
        role=membership.role,
        status=membership.status,
    )


@router.patch("/{user_id}/role", response_model=UserRow)
async def change_role(
    user_id: str,
    body: ChangeRoleRequest,
    db: DbSession,
    tenant_id: TenantId,
    actor_id: ActorId,
) -> UserRow:
    admin_id = await _require_admin(db, tenant_id, actor_id)
    try:
        membership = await users_svc.change_role(
            db,
            tenant_id=tenant_id,
            actor_user_id=admin_id,
            user_id=user_id,
            new_role=body.role,
        )
    except users_svc.MembershipNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="User is not a member of this tenant")
    except users_svc.InviteError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    await db.commit()

    return await _user_row(db, tenant_id, membership.user_id)


@router.post("/{user_id}/deactivate", response_model=UserRow)
async def deactivate(
    user_id: str,
    db: DbSession,
    tenant_id: TenantId,
    actor_id: ActorId,
) -> UserRow:
    admin_id = await _require_admin(db, tenant_id, actor_id)
    try:
        membership = await users_svc.deactivate_user(
            db,
            tenant_id=tenant_id,
            actor_user_id=admin_id,
            user_id=user_id,
        )
    except users_svc.MembershipNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="User is not a member of this tenant")
    except users_svc.InviteError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    await db.commit()

    return await _user_row(db, tenant_id, membership.user_id)


@router.post("/{user_id}/reactivate", response_model=UserRow)
async def reactivate(
    user_id: str,
    db: DbSession,
    tenant_id: TenantId,
    actor_id: ActorId,
) -> UserRow:
    admin_id = await _require_admin(db, tenant_id, actor_id)
    try:
        membership = await users_svc.reactivate_user(
            db,
            tenant_id=tenant_id,
            actor_user_id=admin_id,
            user_id=user_id,
        )
    except users_svc.MembershipNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="User is not a member of this tenant")
    await db.commit()

    return await _user_row(db, tenant_id, membership.user_id)


async def _user_row(db: DbSession, tenant_id: str, user_id: str) -> UserRow:
    rows = await users_svc.list_users(db, tenant_id)
    for r in rows:
        if r["user_id"] == user_id:
            return UserRow(**r)
    raise HTTPException(status.HTTP_404_NOT_FOUND, detail="User not found")
