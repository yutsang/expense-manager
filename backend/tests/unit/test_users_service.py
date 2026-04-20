"""Unit tests for app.services.users — invite / accept / role / deactivate flows.

Uses structural + pure-function assertions for things that don't touch the DB,
plus a minimal in-memory fake session for the DB-backed flows.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest


class _Row:
    """Minimal User/Membership stand-in."""

    def __init__(self, **fields: Any) -> None:
        for k, v in fields.items():
            setattr(self, k, v)


class _FakeDb:
    """An async DB session that holds a handful of rows keyed by class name."""

    def __init__(self) -> None:
        self._rows: dict[str, list[_Row]] = {"User": [], "Membership": [], "AuditEvent": []}
        self._scalar_queue: list[Any] = []

    async def scalar(self, _stmt: Any) -> Any:
        # Tests pre-queue scalar return values; otherwise return None.
        if self._scalar_queue:
            return self._scalar_queue.pop(0)
        return None

    async def execute(self, _stmt: Any) -> Any:
        class _Result:
            def scalars(self_) -> list[Any]:  # noqa: N805
                return []

            def all(self_) -> list[Any]:  # noqa: N805
                return []

        return _Result()

    def add(self, row: Any) -> None:
        name = type(row).__name__
        self._rows.setdefault(name, []).append(row)

    async def flush(self) -> None:
        return None

    async def refresh(self, _row: Any) -> None:
        return None


class TestInviteToken:
    def test_invalid_role_rejected(self) -> None:
        import asyncio

        from app.services.users import InviteError, invite_user

        db = _FakeDb()

        async def _go() -> None:
            await invite_user(
                db,
                tenant_id="t1",
                inviter_user_id="u-admin",
                email="x@example.com",
                role="sysadmin",  # not in ALLOWED_ROLES
            )

        with pytest.raises(InviteError):
            asyncio.get_event_loop().run_until_complete(_go())

    def test_inviting_owner_role_rejected(self) -> None:
        import asyncio

        from app.services.users import InviteError, invite_user

        db = _FakeDb()

        async def _go() -> None:
            await invite_user(
                db,
                tenant_id="t1",
                inviter_user_id="u-admin",
                email="x@example.com",
                role="owner",
            )

        with pytest.raises(InviteError, match="owner"):
            asyncio.get_event_loop().run_until_complete(_go())

    def test_invite_ttl_is_seven_days(self) -> None:
        from app.services.users import INVITE_TTL

        assert INVITE_TTL == timedelta(days=7)

    def test_allowed_roles_locked(self) -> None:
        """The role allow-list should match the DB check constraint."""
        from app.services.users import ALLOWED_ROLES

        expected = {
            "owner",
            "admin",
            "accountant",
            "bookkeeper",
            "approver",
            "viewer",
            "auditor",
            "api_client",
        }
        assert ALLOWED_ROLES == expected


class TestInviteUserNewEmail:
    @pytest.mark.asyncio
    async def test_creates_user_and_membership_when_email_not_known(self) -> None:
        from app.services import users as svc

        db = _FakeDb()
        db._scalar_queue = [None]  # no existing user lookup

        with patch.object(svc, "emit", AsyncMock()) as emit_mock:
            membership, token = await svc.invite_user(
                db,
                tenant_id="t-1",
                inviter_user_id="admin-1",
                email="NewUser@Example.com ",
                role="accountant",
                display_name="New User",
            )

        # Normalized email.
        assert any(u.email == "newuser@example.com" for u in db._rows["User"])
        assert membership.role == "accountant"
        assert membership.status == "invited"
        # Token is a non-trivial URL-safe string; only its hash is stored.
        assert len(token) >= 32
        assert membership.invite_token_hash is not None
        assert membership.invite_token_hash != token
        # Audit event emitted.
        emit_mock.assert_awaited_once()
        assert emit_mock.await_args.kwargs["action"] == "user.invited"

    @pytest.mark.asyncio
    async def test_invite_token_hash_uses_sha256(self) -> None:
        from app.core.security import hash_token
        from app.services import users as svc

        db = _FakeDb()
        db._scalar_queue = [None]

        with patch.object(svc, "emit", AsyncMock()):
            membership, token = await svc.invite_user(
                db,
                tenant_id="t-1",
                inviter_user_id="admin-1",
                email="a@b.com",
                role="viewer",
            )

        assert membership.invite_token_hash == hash_token(token)

    @pytest.mark.asyncio
    async def test_rejects_invite_when_already_active_member(self) -> None:
        from app.services import users as svc

        db = _FakeDb()
        existing_user = _Row(id="u-existing", email="dup@example.com")
        existing_membership = _Row(
            id="m1",
            tenant_id="t-1",
            user_id="u-existing",
            role="accountant",
            status="active",
        )
        db._scalar_queue = [existing_user, existing_membership]

        with (
            patch.object(svc, "emit", AsyncMock()),
            pytest.raises(svc.InviteError, match="already a member"),
        ):
            await svc.invite_user(
                db,
                tenant_id="t-1",
                inviter_user_id="admin-1",
                email="dup@example.com",
                role="viewer",
            )


class TestAcceptInvite:
    @pytest.mark.asyncio
    async def test_rejects_unknown_token(self) -> None:
        from app.services import users as svc

        db = _FakeDb()
        db._scalar_queue = [None]

        with pytest.raises(svc.InviteError, match="Invalid or expired"):
            await svc.accept_invite(
                db, invite_token="totally-unknown-token-xxxxxxxxx", password="abc12345678ABC!"
            )

    @pytest.mark.asyncio
    async def test_rejects_expired_invite(self) -> None:
        from app.core.security import hash_token
        from app.services import users as svc

        token = "fake-token-abcdefghij"
        db = _FakeDb()
        expired_membership = _Row(
            id="m-exp",
            tenant_id="t-1",
            user_id="u-1",
            status="invited",
            invite_token_hash=hash_token(token),
            invite_expires_at=datetime.now(tz=UTC) - timedelta(days=1),
        )
        db._scalar_queue = [expired_membership]

        with pytest.raises(svc.InviteError, match="expired"):
            await svc.accept_invite(db, invite_token=token, password="longer-than-twelve-chars!")

    @pytest.mark.asyncio
    async def test_rejects_already_used_invite(self) -> None:
        from app.core.security import hash_token
        from app.services import users as svc

        token = "fake-used-token-abcdefghij"
        db = _FakeDb()
        used = _Row(
            id="m-used",
            tenant_id="t-1",
            user_id="u-1",
            status="active",
            invite_token_hash=hash_token(token),
            invite_expires_at=datetime.now(tz=UTC) + timedelta(days=1),
        )
        db._scalar_queue = [used]

        with pytest.raises(svc.InviteError, match="already"):
            await svc.accept_invite(db, invite_token=token, password="longer-than-twelve-chars!")


class TestChangeRoleAndDeactivate:
    @pytest.mark.asyncio
    async def test_deactivating_owner_is_forbidden(self) -> None:
        from app.services import users as svc

        db = _FakeDb()
        owner_m = _Row(
            id="m-own",
            tenant_id="t-1",
            user_id="u-owner",
            role="owner",
            status="active",
            version=1,
        )
        db._scalar_queue = [owner_m]

        with pytest.raises(svc.InviteError, match="owner"):
            await svc.deactivate_user(
                db,
                tenant_id="t-1",
                actor_user_id="admin-1",
                user_id="u-owner",
            )

    @pytest.mark.asyncio
    async def test_change_role_unknown_user_raises_not_found(self) -> None:
        from app.services import users as svc

        db = _FakeDb()
        db._scalar_queue = [None]

        with pytest.raises(svc.MembershipNotFoundError):
            await svc.change_role(
                db,
                tenant_id="t-1",
                actor_user_id="admin-1",
                user_id="u-ghost",
                new_role="viewer",
            )

    @pytest.mark.asyncio
    async def test_change_role_emits_before_after_audit(self) -> None:
        from app.services import users as svc

        db = _FakeDb()
        m = _Row(
            id="m-1",
            tenant_id="t-1",
            user_id="u-1",
            role="viewer",
            status="active",
            version=1,
            updated_at=datetime.now(tz=UTC),
        )
        db._scalar_queue = [m]

        with patch.object(svc, "emit", AsyncMock()) as emit_mock:
            await svc.change_role(
                db,
                tenant_id="t-1",
                actor_user_id="admin-1",
                user_id="u-1",
                new_role="accountant",
            )

        emit_mock.assert_awaited_once()
        kwargs = emit_mock.await_args.kwargs
        assert kwargs["action"] == "user.role_changed"
        assert kwargs["before"] == {"role": "viewer"}
        assert kwargs["after"] == {"role": "accountant"}


class TestRouterRegistration:
    def test_users_router_registered_on_app(self) -> None:
        """The /v1/users routes must be wired into the FastAPI app."""
        import os

        os.environ.setdefault("SECRET_KEY", "test-secret-key-at-least-32-chars-long!!")
        os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://a:b@c/d")
        import importlib

        # Fresh import to avoid stale state.
        users_router = importlib.import_module("app.api.v1.users")
        paths = [route.path for route in users_router.router.routes]
        assert "/users" in paths
        assert "/users/invite" in paths
        assert "/users/accept-invite" in paths
        assert "/users/{user_id}/role" in paths
        assert "/users/{user_id}/deactivate" in paths
