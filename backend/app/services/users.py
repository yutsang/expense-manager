"""User + membership management: invite, accept, change role, deactivate.

Scope follows plan Track F1. Enforces tenant isolation (all mutations scoped
to the current tenant's memberships) and emits audit events for every
change so compliance can trace who-gave-access-to-whom.

Invite flow:
    1. POST /users/invite (owner/admin) → generates a secret token, stores
       only its SHA-256 hash on the new Membership row (status=invited),
       and returns the raw token to the caller once. The caller is
       expected to email the invite link to the user.
    2. POST /users/accept-invite with (token, password, display_name) →
       looks up the Membership by token hash, creates (or reuses) a User,
       sets status=active, clears the token fields.
    3. PATCH /users/{user_id}/role (owner/admin) → change role.
    4. POST /users/{user_id}/deactivate (owner/admin) → status=suspended.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.emitter import emit
from app.core.logging import get_logger
from app.core.security import generate_secure_token, hash_password, hash_token
from app.infra.models import Membership, User

log = get_logger(__name__)

INVITE_TTL = timedelta(days=7)

ALLOWED_ROLES = frozenset(
    {
        "owner",
        "admin",
        "accountant",
        "bookkeeper",
        "approver",
        "viewer",
        "auditor",
        "api_client",
    }
)


class InviteError(ValueError):
    pass


class MembershipNotFoundError(ValueError):
    pass


async def list_users(db: AsyncSession, tenant_id: str) -> list[dict]:
    """Return active + invited + suspended members of the tenant."""
    rows = await db.execute(
        select(User, Membership)
        .join(Membership, Membership.user_id == User.id)
        .where(Membership.tenant_id == tenant_id)
        .order_by(User.display_name)
    )
    result: list[dict] = []
    for user, membership in rows.all():
        result.append(
            {
                "user_id": user.id,
                "email": user.email,
                "display_name": user.display_name,
                "role": membership.role,
                "status": membership.status,
                "invited_at": membership.invited_at,
                "joined_at": membership.joined_at,
                "invited_by": membership.invited_by,
                "last_login_at": user.last_login_at,
                "membership_id": membership.id,
            }
        )
    return result


async def invite_user(
    db: AsyncSession,
    *,
    tenant_id: str,
    inviter_user_id: str,
    email: str,
    role: str,
    display_name: str | None = None,
) -> tuple[Membership, str]:
    """Create an invited Membership. Returns (membership, raw_invite_token).

    Raises ``InviteError`` if the email already has an active or invited
    membership in this tenant, or if ``role`` is not recognised.
    """
    role_norm = role.lower().strip()
    if role_norm not in ALLOWED_ROLES:
        raise InviteError(f"Unknown role: {role}")
    if role_norm == "owner":
        # Owner promotion is an explicit admin flow, not an invite.
        raise InviteError("Cannot invite a new owner; use change-role on an existing active member")

    email_norm = email.lower().strip()

    existing_user = await db.scalar(select(User).where(User.email == email_norm))

    if existing_user is not None:
        existing_membership = await db.scalar(
            select(Membership).where(
                Membership.tenant_id == tenant_id,
                Membership.user_id == existing_user.id,
            )
        )
        if existing_membership is not None:
            if existing_membership.status == "active":
                raise InviteError(f"{email_norm} is already a member of this tenant")
            # Re-issue invite for a previously-invited/suspended member.
            return await _reissue_invite(
                db,
                membership=existing_membership,
                inviter_user_id=inviter_user_id,
                tenant_id=tenant_id,
                role=role_norm,
            )

        user = existing_user
    else:
        user = User(
            id=str(uuid.uuid4()),
            email=email_norm,
            display_name=display_name or email_norm.split("@")[0],
            # Not-yet-set; accept_invite overwrites with argon2 hash. The
            # single-char value can never match any argon2 output.
            password_hash="!",  # noqa: S106
            version=1,
        )
        db.add(user)
        await db.flush()

    now = datetime.now(tz=UTC)
    raw_token = generate_secure_token()
    membership = Membership(
        id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        user_id=user.id,
        role=role_norm,
        status="invited",
        invited_by=inviter_user_id,
        invited_at=now,
        invite_token_hash=hash_token(raw_token),
        invite_expires_at=now + INVITE_TTL,
        version=1,
    )
    db.add(membership)
    await db.flush()

    await emit(
        db,
        action="user.invited",
        entity_type="membership",
        entity_id=membership.id,
        actor_type="user",
        actor_id=inviter_user_id,
        tenant_id=tenant_id,
        metadata={"email": email_norm, "role": role_norm},
    )
    log.info("user.invited", tenant_id=tenant_id, email=email_norm, role=role_norm)
    return membership, raw_token


async def _reissue_invite(
    db: AsyncSession,
    *,
    membership: Membership,
    inviter_user_id: str,
    tenant_id: str,
    role: str,
) -> tuple[Membership, str]:
    now = datetime.now(tz=UTC)
    raw_token = generate_secure_token()
    membership.invite_token_hash = hash_token(raw_token)
    membership.invite_expires_at = now + INVITE_TTL
    membership.invited_at = now
    membership.invited_by = inviter_user_id
    membership.role = role
    membership.status = "invited"
    membership.version += 1
    membership.updated_at = now
    await db.flush()

    await emit(
        db,
        action="user.invite_resent",
        entity_type="membership",
        entity_id=membership.id,
        actor_type="user",
        actor_id=inviter_user_id,
        tenant_id=tenant_id,
        metadata={"role": role},
    )
    return membership, raw_token


async def accept_invite(
    db: AsyncSession,
    *,
    invite_token: str,
    password: str,
    display_name: str | None = None,
) -> Membership:
    """Complete an invite: verify token, set password, activate the membership."""
    token_hash = hash_token(invite_token)
    membership = await db.scalar(
        select(Membership).where(Membership.invite_token_hash == token_hash)
    )
    if membership is None:
        raise InviteError("Invalid or expired invite token")
    if membership.status != "invited":
        raise InviteError("This invite has already been used")
    if membership.invite_expires_at is not None and membership.invite_expires_at < datetime.now(
        tz=UTC
    ):
        raise InviteError("Invite token has expired")

    user = await db.scalar(select(User).where(User.id == membership.user_id))
    if user is None:
        raise InviteError("Invited user no longer exists")

    now = datetime.now(tz=UTC)
    user.password_hash = hash_password(password)
    if display_name:
        user.display_name = display_name
    user.email_verified_at = now
    user.updated_at = now
    user.version += 1

    membership.status = "active"
    membership.joined_at = now
    membership.invite_token_hash = None
    membership.invite_expires_at = None
    membership.updated_at = now
    membership.version += 1
    await db.flush()

    await emit(
        db,
        action="user.invite_accepted",
        entity_type="membership",
        entity_id=membership.id,
        actor_type="user",
        actor_id=user.id,
        tenant_id=membership.tenant_id,
        metadata={"email": user.email, "role": membership.role},
    )
    log.info("user.invite_accepted", tenant_id=membership.tenant_id, user_id=user.id)
    return membership


async def change_role(
    db: AsyncSession,
    *,
    tenant_id: str,
    actor_user_id: str,
    user_id: str,
    new_role: str,
) -> Membership:
    role_norm = new_role.lower().strip()
    if role_norm not in ALLOWED_ROLES:
        raise InviteError(f"Unknown role: {new_role}")

    membership = await db.scalar(
        select(Membership).where(
            Membership.tenant_id == tenant_id,
            Membership.user_id == user_id,
        )
    )
    if membership is None:
        raise MembershipNotFoundError("User is not a member of this tenant")

    old_role = membership.role
    if old_role == role_norm:
        return membership

    membership.role = role_norm
    membership.version += 1
    membership.updated_at = datetime.now(tz=UTC)
    await db.flush()

    await emit(
        db,
        action="user.role_changed",
        entity_type="membership",
        entity_id=membership.id,
        actor_type="user",
        actor_id=actor_user_id,
        tenant_id=tenant_id,
        before={"role": old_role},
        after={"role": role_norm},
        metadata={"target_user_id": user_id},
    )
    return membership


async def deactivate_user(
    db: AsyncSession,
    *,
    tenant_id: str,
    actor_user_id: str,
    user_id: str,
) -> Membership:
    membership = await db.scalar(
        select(Membership).where(
            Membership.tenant_id == tenant_id,
            Membership.user_id == user_id,
        )
    )
    if membership is None:
        raise MembershipNotFoundError("User is not a member of this tenant")
    if membership.role == "owner":
        raise InviteError("Cannot deactivate the tenant owner")
    if membership.status == "suspended":
        return membership

    old_status = membership.status
    membership.status = "suspended"
    membership.version += 1
    membership.updated_at = datetime.now(tz=UTC)
    await db.flush()

    await emit(
        db,
        action="user.deactivated",
        entity_type="membership",
        entity_id=membership.id,
        actor_type="user",
        actor_id=actor_user_id,
        tenant_id=tenant_id,
        before={"status": old_status},
        after={"status": "suspended"},
        metadata={"target_user_id": user_id},
    )
    return membership


async def reactivate_user(
    db: AsyncSession,
    *,
    tenant_id: str,
    actor_user_id: str,
    user_id: str,
) -> Membership:
    membership = await db.scalar(
        select(Membership).where(
            Membership.tenant_id == tenant_id,
            Membership.user_id == user_id,
        )
    )
    if membership is None:
        raise MembershipNotFoundError("User is not a member of this tenant")
    if membership.status == "active":
        return membership

    old_status = membership.status
    membership.status = "active"
    membership.version += 1
    membership.updated_at = datetime.now(tz=UTC)
    await db.flush()

    await emit(
        db,
        action="user.reactivated",
        entity_type="membership",
        entity_id=membership.id,
        actor_type="user",
        actor_id=actor_user_id,
        tenant_id=tenant_id,
        before={"status": old_status},
        after={"status": "active"},
        metadata={"target_user_id": user_id},
    )
    return membership
