"""Auth service — signup, login, logout, token refresh.

Does NOT import from sibling services. Uses app.core.security and app.infra.models.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.core.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    verify_password,
)
from app.core.tenant import set_rls_tenant
from app.infra.models import Membership, Session, Tenant, User
from app.services.onboarding import setup_tenant

log = get_logger(__name__)

_REFRESH_TTL_DAYS = 30


class AuthError(ValueError):
    pass


class UserAlreadyExistsError(AuthError):
    pass


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


async def signup(
    db: AsyncSession,
    email: str,
    password: str,
    display_name: str,
    tenant_name: str,
    country: str,
    currency: str = "USD",
) -> tuple[User, Tenant, str, str]:
    """Create tenant + owner user + membership.

    Returns (user, tenant, access_token, refresh_token_raw).
    Raises UserAlreadyExistsError if email already registered.
    """
    # Check for duplicate email
    existing = await db.scalar(select(User).where(User.email == email.lower()))
    if existing is not None:
        raise UserAlreadyExistsError(f"Email already registered: {email}")

    tenant = Tenant(
        name=tenant_name,
        legal_name=tenant_name,
        country=country,
        functional_currency=currency,
        status="trial",
    )
    db.add(tenant)
    await db.flush()

    user = User(
        email=email.lower(),
        display_name=display_name,
        password_hash=hash_password(password),
    )
    db.add(user)
    await db.flush()

    membership = Membership(
        tenant_id=tenant.id,
        user_id=user.id,
        role="owner",
        status="active",
        joined_at=datetime.now(tz=UTC),
    )
    db.add(membership)
    await db.flush()

    # Provision CoA, periods, and a default bank account so the new tenant lands
    # on a populated dashboard instead of an empty shell. Any failure here rolls
    # back the whole signup via the router's transaction boundary.
    await set_rls_tenant(db, tenant.id)
    await setup_tenant(
        db,
        tenant_id=tenant.id,
        actor_id=user.id,
        company_name=tenant_name,
        legal_name=tenant_name,
        country=country,
        functional_currency=currency,
        fiscal_year_start_month=1,
        coa_template="general",
        bank_account_name="Primary Operating Account",
        bank_currency=currency,
    )

    access_token = create_access_token(user_id=user.id, tenant_id=tenant.id)
    refresh_raw, refresh_hash = create_refresh_token(user_id=user.id)

    session = Session(
        user_id=user.id,
        refresh_token_hash=refresh_hash,
        expires_at=datetime.now(tz=UTC) + timedelta(days=_REFRESH_TTL_DAYS),
    )
    db.add(session)
    await db.flush()
    await db.refresh(user)
    await db.refresh(tenant)

    log.info("auth.signup", user_id=user.id, tenant_id=tenant.id)
    return user, tenant, access_token, refresh_raw


async def login(
    db: AsyncSession,
    email: str,
    password: str,
) -> tuple[User, str, str, list[str]]:
    """Verify credentials.

    Returns (user, access_token, refresh_token_raw, tenant_ids).
    Raises AuthError if credentials are invalid.
    """
    user = await db.scalar(select(User).where(User.email == email.lower()))
    if user is None or not verify_password(password, user.password_hash):
        raise AuthError("Invalid email or password")

    # Collect all active tenant memberships
    memberships_result = await db.execute(
        select(Membership).where(
            Membership.user_id == user.id,
            Membership.status == "active",
        )
    )
    memberships = list(memberships_result.scalars())
    tenant_ids = [m.tenant_id for m in memberships]

    # Use the first tenant for the access token (caller can switch later)
    primary_tenant_id = tenant_ids[0] if tenant_ids else None

    access_token = create_access_token(user_id=user.id, tenant_id=primary_tenant_id)
    refresh_raw, refresh_hash = create_refresh_token(user_id=user.id)

    session = Session(
        user_id=user.id,
        refresh_token_hash=refresh_hash,
        expires_at=datetime.now(tz=UTC) + timedelta(days=_REFRESH_TTL_DAYS),
    )
    db.add(session)

    user.last_login_at = datetime.now(tz=UTC)
    user.login_failure_count = 0
    await db.flush()

    log.info("auth.login", user_id=user.id)
    return user, access_token, refresh_raw, tenant_ids


async def logout(db: AsyncSession, user_id: str, refresh_token_raw: str) -> None:
    """Revoke the session identified by the raw refresh token."""
    token_hash = _hash_token(refresh_token_raw)
    session = await db.scalar(
        select(Session).where(
            Session.user_id == user_id,
            Session.refresh_token_hash == token_hash,
        )
    )
    if session is not None:
        now = datetime.now(tz=UTC)
        # Mark revoked by setting expires_at to the past (no revoked_at column on model)
        session.expires_at = now
        await db.flush()
    log.info("auth.logout", user_id=user_id)


async def refresh(
    db: AsyncSession,
    refresh_token_raw: str,
) -> tuple[str, str]:
    """Rotate refresh token and return new (access_token, refresh_token_raw).

    Raises AuthError if the token is not found or is expired/revoked.
    """
    token_hash = _hash_token(refresh_token_raw)
    now = datetime.now(tz=UTC)

    session = await db.scalar(
        select(Session).where(
            Session.refresh_token_hash == token_hash,
            Session.expires_at > now,
        )
    )
    if session is None:
        raise AuthError("Refresh token is invalid or expired")

    user = await db.scalar(select(User).where(User.id == session.user_id))
    if user is None:
        raise AuthError("User not found")

    # Collect primary tenant
    membership = await db.scalar(
        select(Membership).where(
            Membership.user_id == user.id,
            Membership.status == "active",
        )
    )
    primary_tenant_id = membership.tenant_id if membership else None

    # Revoke old session
    session.expires_at = now
    await db.flush()

    # Issue new tokens
    access_token = create_access_token(user_id=user.id, tenant_id=primary_tenant_id)
    refresh_raw, refresh_hash = create_refresh_token(user_id=user.id)

    new_session = Session(
        user_id=user.id,
        refresh_token_hash=refresh_hash,
        expires_at=now + timedelta(days=_REFRESH_TTL_DAYS),
    )
    db.add(new_session)
    await db.flush()

    log.info("auth.refresh", user_id=user.id)
    return access_token, refresh_raw
