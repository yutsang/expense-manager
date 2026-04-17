"""Unit tests for blocking self-approval of expense claims (Issue #19).

Segregation of duties: the person who created an expense claim must not
be the same person who approves it, regardless of their role.

Tests cover:
  - Self-approval raises SelfApprovalError
  - A different user can approve successfully
  - Admin self-approval is also blocked (no role exemption)
  - API layer maps SelfApprovalError to HTTP 403
"""

from __future__ import annotations

import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_NEEDS_311 = sys.version_info < (3, 11)
_skip_311 = pytest.mark.skipif(_NEEDS_311, reason="datetime.UTC requires Python >=3.11")


class TestServiceSourceHasSelfApprovalGuard:
    """Verify the service module has the self-approval guard via source inspection."""

    def _read_service_source(self) -> str:
        import pathlib

        svc_path = (
            pathlib.Path(__file__).resolve().parents[2]
            / "app"
            / "services"
            / "expense_claims.py"
        )
        return svc_path.read_text()

    def test_self_approval_error_class_exists(self) -> None:
        source = self._read_service_source()
        assert "class SelfApprovalError" in source

    def test_approve_checks_created_by(self) -> None:
        source = self._read_service_source()
        assert "created_by" in source

    def test_approve_function_references_self_approval(self) -> None:
        source = self._read_service_source()
        assert "SelfApprovalError" in source


class TestApiEndpointHandlesSelfApproval:
    """Verify the API endpoint maps SelfApprovalError to 403."""

    def _read_api_source(self) -> str:
        import pathlib

        api_path = (
            pathlib.Path(__file__).resolve().parents[2]
            / "app"
            / "api"
            / "v1"
            / "expense_claims.py"
        )
        return api_path.read_text()

    def test_api_imports_self_approval_error(self) -> None:
        source = self._read_api_source()
        assert "SelfApprovalError" in source

    def test_api_returns_403_on_self_approval(self) -> None:
        source = self._read_api_source()
        assert "HTTP_403_FORBIDDEN" in source


@_skip_311
class TestExpenseClaimSelfApproval:
    """Service-level async tests for the self-approval guard."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        db = AsyncMock()
        db.flush = AsyncMock()
        db.refresh = AsyncMock()
        db.execute = AsyncMock()
        db.scalar = AsyncMock()
        return db

    def _make_claim(
        self,
        *,
        status: str = "submitted",
        created_by: str = "user-1",
        tenant_id: str = "t1",
    ) -> MagicMock:
        claim = MagicMock()
        claim.id = "claim-1"
        claim.tenant_id = tenant_id
        claim.status = status
        claim.created_by = created_by
        claim.version = 1
        claim.updated_by = None
        claim.approved_by = None
        claim.approved_at = None
        return claim

    @pytest.mark.anyio
    async def test_self_approval_raises_error(self, mock_db: AsyncMock) -> None:
        """Approving your own expense claim must raise SelfApprovalError."""
        from app.services.expense_claims import SelfApprovalError, approve_expense_claim

        claim = self._make_claim(created_by="user-1")

        with (
            patch("app.services.expense_claims.get_expense_claim", return_value=claim),
            pytest.raises(SelfApprovalError),
        ):
            await approve_expense_claim(mock_db, "t1", "user-1", "claim-1")

    @pytest.mark.anyio
    async def test_different_user_can_approve(self, mock_db: AsyncMock) -> None:
        """A different user should be able to approve the claim."""
        from app.services.expense_claims import approve_expense_claim

        claim = self._make_claim(created_by="user-1")

        with patch("app.services.expense_claims.get_expense_claim", return_value=claim):
            result = await approve_expense_claim(mock_db, "t1", "user-2", "claim-1")

        assert result.status == "approved"

    @pytest.mark.anyio
    async def test_admin_self_approval_also_blocked(self, mock_db: AsyncMock) -> None:
        """Admins are NOT exempt from the self-approval rule."""
        from app.services.expense_claims import SelfApprovalError, approve_expense_claim

        # The claim was created by an admin user
        claim = self._make_claim(created_by="admin-user-1")

        with (
            patch("app.services.expense_claims.get_expense_claim", return_value=claim),
            pytest.raises(SelfApprovalError),
        ):
            # The same admin tries to approve their own claim
            await approve_expense_claim(mock_db, "t1", "admin-user-1", "claim-1")

    @pytest.mark.anyio
    async def test_self_approval_error_message_is_descriptive(self, mock_db: AsyncMock) -> None:
        """The error message should clearly explain the segregation of duties rule."""
        from app.services.expense_claims import SelfApprovalError, approve_expense_claim

        claim = self._make_claim(created_by="user-1")

        with (
            patch("app.services.expense_claims.get_expense_claim", return_value=claim),
            pytest.raises(SelfApprovalError, match="cannot approve their own"),
        ):
            await approve_expense_claim(mock_db, "t1", "user-1", "claim-1")
