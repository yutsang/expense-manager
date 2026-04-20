"""Unit tests for the audit chain verification ARQ worker.

Covers:
  - The worker discovers every tenant that has audit events.
  - OK / broken / error counts roll up correctly.
  - Broken chains surface to Sentry (when the SDK is installed).
  - The worker does not fail-fast if one tenant's verification errors; it
    still proceeds through the remaining tenants.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _fake_result(is_valid: bool, chain_length: int = 3, break_id: str | None = None) -> dict[str, Any]:
    return {
        "id": "verification-uuid",
        "is_valid": is_valid,
        "chain_length": chain_length,
        "break_at_event_id": break_id,
        "last_event_id": "event-last",
        "error_message": None if is_valid else f"Hash mismatch at event {break_id}",
        "verified_at": datetime.now(tz=UTC),
    }


class _FakeSession:
    """Minimal AsyncSessionLocal stand-in — context manager that yields a DB."""

    def __init__(self, tenant_ids: list[str] | None = None) -> None:
        self._tenant_ids = tenant_ids
        self.committed = False
        self.rolled_back = False

    async def __aenter__(self) -> _FakeSession:
        return self

    async def __aexit__(self, *args: Any) -> None:
        return None

    async def execute(self, _stmt: Any) -> Any:
        # Only the tenant discovery query is expected via execute(); it should
        # return rows shaped like ``(tenant_id,)``.
        result = MagicMock()
        if self._tenant_ids is not None:
            result.all = MagicMock(return_value=[(tid,) for tid in self._tenant_ids])
        else:
            result.all = MagicMock(return_value=[])
        return result

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True


@pytest.mark.asyncio
async def test_worker_reports_all_ok_when_every_chain_valid() -> None:
    from app.workers import verify_audit_chain as mod

    tenants = ["t-1", "t-2", "t-3"]

    def _session_factory() -> _FakeSession:
        # Only the first session call performs the tenant discovery.
        # Subsequent calls verify a tenant; they don't need the list.
        session = _FakeSession(tenant_ids=tenants if _session_factory.first else None)
        _session_factory.first = False
        return session

    _session_factory.first = True

    with (
        patch.object(mod, "AsyncSessionLocal", side_effect=_session_factory),
        patch.object(mod, "set_rls_tenant", AsyncMock()),
        patch.object(mod, "verify_chain", AsyncMock(return_value=_fake_result(is_valid=True))),
    ):
        result = await mod.verify_all_tenants({})

    assert result["tenants_verified"] == 3
    assert result["ok"] == 3
    assert result["broken"] == 0
    assert result["errors"] == 0
    assert result["broken_tenants"] == []


@pytest.mark.asyncio
async def test_worker_flags_broken_chain_and_continues() -> None:
    from app.workers import verify_audit_chain as mod

    tenants = ["t-ok", "t-broken"]

    def _session_factory() -> _FakeSession:
        session = _FakeSession(tenant_ids=tenants if _session_factory.first else None)
        _session_factory.first = False
        return session

    _session_factory.first = True

    def verify_side_effect(_db: Any, tenant_id: str) -> dict[str, Any]:
        if tenant_id == "t-broken":
            return _fake_result(is_valid=False, break_id="evt-77")
        return _fake_result(is_valid=True)

    with (
        patch.object(mod, "AsyncSessionLocal", side_effect=_session_factory),
        patch.object(mod, "set_rls_tenant", AsyncMock()),
        patch.object(mod, "verify_chain", AsyncMock(side_effect=verify_side_effect)),
        patch.object(mod, "_alert_broken_chain") as alert,
    ):
        result = await mod.verify_all_tenants({})

    assert result["ok"] == 1
    assert result["broken"] == 1
    assert result["errors"] == 0
    broken_list = result["broken_tenants"]
    assert len(broken_list) == 1
    assert broken_list[0]["tenant_id"] == "t-broken"
    assert broken_list[0]["break_at_event_id"] == "evt-77"
    alert.assert_called_once()
    # First positional arg is the tenant_id, second is the verify result.
    call_args = alert.call_args
    assert call_args.args[0] == "t-broken"


@pytest.mark.asyncio
async def test_worker_swallows_tenant_errors() -> None:
    from app.workers import verify_audit_chain as mod

    tenants = ["t-a", "t-b"]

    def _session_factory() -> _FakeSession:
        session = _FakeSession(tenant_ids=tenants if _session_factory.first else None)
        _session_factory.first = False
        return session

    _session_factory.first = True

    async def verify_side_effect(_db: Any, tenant_id: str) -> dict[str, Any]:
        if tenant_id == "t-a":
            raise RuntimeError("connection blew up")
        return _fake_result(is_valid=True)

    with (
        patch.object(mod, "AsyncSessionLocal", side_effect=_session_factory),
        patch.object(mod, "set_rls_tenant", AsyncMock()),
        patch.object(mod, "verify_chain", AsyncMock(side_effect=verify_side_effect)),
    ):
        result = await mod.verify_all_tenants({})

    assert result["errors"] == 1
    assert result["ok"] == 1  # t-b still verified
    assert result["broken"] == 0


def test_alert_broken_chain_is_noop_without_sentry() -> None:
    """The alert helper must never raise even if Sentry is missing."""
    from app.workers.verify_audit_chain import _alert_broken_chain

    # Call with a minimal result dict; any import error swallows silently.
    _alert_broken_chain(
        "tenant-x",
        {
            "break_at_event_id": "e1",
            "chain_length": 5,
            "last_event_id": "e5",
            "error_message": "mismatch",
        },
    )
    # No assertion needed — success is not raising.


def test_alert_broken_chain_tags_tenant_in_sentry() -> None:
    from app.workers import verify_audit_chain as mod

    sentry = MagicMock()
    sentry.push_scope.return_value.__enter__ = MagicMock(return_value=MagicMock())
    sentry.push_scope.return_value.__exit__ = MagicMock(return_value=False)

    with patch.dict("sys.modules", {"sentry_sdk": sentry}):
        mod._alert_broken_chain(
            "tenant-y",
            {
                "break_at_event_id": "e2",
                "chain_length": 10,
                "last_event_id": "e10",
                "error_message": "mismatch",
            },
        )

    sentry.capture_message.assert_called_once()
    args, kwargs = sentry.capture_message.call_args
    assert "tenant-y" in args[0]
    assert kwargs.get("level") == "error"
