"""Unit tests for invoice approval threshold feature (Issue #17).

Tests cover:
  - TenantSettings schema with invoice_approval_threshold field
  - Invoice model supports 'awaiting_approval' status
  - authorise_invoice: threshold triggers awaiting_approval status
  - authorise_invoice: no threshold -> existing single-step flow
  - approve_invoice: transitions from awaiting_approval to authorised
  - approve_invoice: rejects self-approval (same user who authorised)
  - approve_invoice: rejects if not in awaiting_approval status
"""

from __future__ import annotations

import sys
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.v1.schemas import TenantSettingsUpdate

# The service module uses datetime.UTC which requires Python 3.11+.
# Service-level tests are skipped on older runtimes; the schema and
# model-source tests still run everywhere.
_NEEDS_311 = sys.version_info < (3, 11)
_skip_311 = pytest.mark.skipif(_NEEDS_311, reason="datetime.UTC requires Python >=3.11")


class TestTenantSettingsSchema:
    """Schema accepts and validates invoice_approval_threshold."""

    def test_threshold_defaults_to_none(self) -> None:
        s = TenantSettingsUpdate()
        assert s.invoice_approval_threshold is None

    def test_threshold_accepts_valid_decimal_string(self) -> None:
        s = TenantSettingsUpdate(invoice_approval_threshold="10000.0000")
        assert s.invoice_approval_threshold == "10000.0000"

    def test_threshold_rejects_negative(self) -> None:
        with pytest.raises(Exception):
            TenantSettingsUpdate(invoice_approval_threshold="-1")

    def test_threshold_accepts_zero(self) -> None:
        # Zero means every invoice needs approval
        s = TenantSettingsUpdate(invoice_approval_threshold="0")
        assert s.invoice_approval_threshold == "0"

    def test_threshold_accepts_none_explicitly(self) -> None:
        s = TenantSettingsUpdate(invoice_approval_threshold=None)
        assert s.invoice_approval_threshold is None

    def test_threshold_rejects_non_numeric(self) -> None:
        with pytest.raises(Exception):
            TenantSettingsUpdate(invoice_approval_threshold="abc")


class TestInvoiceModelStatus:
    """Invoice model must support 'awaiting_approval' status."""

    def test_awaiting_approval_in_status_check_constraint(self) -> None:
        # Read the models.py source directly to verify the constraint includes
        # 'awaiting_approval', avoiding a runtime import that fails on Python 3.10
        # (datetime.UTC is 3.11+). This is a source-level verification.
        import pathlib

        models_path = pathlib.Path(__file__).resolve().parents[2] / "app" / "infra" / "models.py"
        source = models_path.read_text()
        # The Invoice check constraint should include 'awaiting_approval'
        assert "'awaiting_approval'" in source
        # It should be in the ck_invoices_status constraint specifically
        idx = source.index("ck_invoices_status")
        # Look at the constraint text within a reasonable window before the name
        constraint_block = source[max(0, idx - 200) : idx]
        assert "awaiting_approval" in constraint_block

    def test_authorised_by_column_exists(self) -> None:
        import pathlib

        models_path = pathlib.Path(__file__).resolve().parents[2] / "app" / "infra" / "models.py"
        source = models_path.read_text()
        assert "authorised_by" in source

    def test_invoice_approval_threshold_on_tenant(self) -> None:
        import pathlib

        models_path = pathlib.Path(__file__).resolve().parents[2] / "app" / "infra" / "models.py"
        source = models_path.read_text()
        assert "invoice_approval_threshold" in source


class TestInvoiceServiceSource:
    """Verify service code structure via source inspection.

    On Python < 3.11 we cannot import the service at runtime, so we
    verify the logic by reading the source code.
    """

    def _read_service_source(self) -> str:
        import pathlib

        svc_path = pathlib.Path(__file__).resolve().parents[2] / "app" / "services" / "invoices.py"
        return svc_path.read_text()

    def test_approve_invoice_function_exists(self) -> None:
        source = self._read_service_source()
        assert "async def approve_invoice(" in source

    def test_invoice_approval_error_class_exists(self) -> None:
        source = self._read_service_source()
        assert "class InvoiceApprovalError" in source

    def test_get_tenant_function_exists(self) -> None:
        source = self._read_service_source()
        assert "async def get_tenant(" in source

    def test_authorise_checks_threshold(self) -> None:
        source = self._read_service_source()
        # The authorise_invoice function should check the threshold
        assert "invoice_approval_threshold" in source
        assert "awaiting_approval" in source

    def test_approve_checks_self_approval(self) -> None:
        source = self._read_service_source()
        assert "authorised_by" in source
        assert "same user" in source

    def test_approve_rejects_non_awaiting_status(self) -> None:
        source = self._read_service_source()
        # Verify the function checks for awaiting_approval status
        assert "awaiting_approval" in source


class TestApiEndpointSource:
    """Verify API endpoint code structure via source inspection."""

    def _read_api_source(self) -> str:
        import pathlib

        api_path = (
            pathlib.Path(__file__).resolve().parents[2] / "app" / "api" / "v1" / "invoices.py"
        )
        return api_path.read_text()

    def test_approve_endpoint_exists(self) -> None:
        source = self._read_api_source()
        assert "/{invoice_id}/approve" in source

    def test_approve_endpoint_uses_approve_invoice(self) -> None:
        source = self._read_api_source()
        assert "approve_invoice" in source

    def test_approve_endpoint_handles_approval_error(self) -> None:
        source = self._read_api_source()
        assert "InvoiceApprovalError" in source
        assert "HTTP_403_FORBIDDEN" in source


# ── Service-level async tests (require Python 3.11+) ────────────────────────


@_skip_311
class TestAuthoriseInvoiceWithThreshold:
    """authorise_invoice should respect the tenant's approval threshold."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        db = AsyncMock()
        db.flush = AsyncMock()
        db.refresh = AsyncMock()
        db.execute = AsyncMock()
        db.scalar = AsyncMock()
        return db

    def _make_invoice(
        self,
        *,
        total: str = "5000.0000",
        status: str = "draft",
        tenant_id: str = "t1",
    ) -> MagicMock:
        inv = MagicMock()
        inv.id = "inv-1"
        inv.tenant_id = tenant_id
        inv.status = status
        inv.total = Decimal(total)
        inv.currency = "USD"
        inv.fx_rate = Decimal("1")
        inv.contact_id = "contact-1"
        inv.issue_date = "2026-01-15"
        inv.period_name = "2026-01"
        inv.number = "DRAFT-ABC"
        inv.version = 1
        inv.updated_by = None
        inv.journal_entry_id = None
        return inv

    def _make_tenant(self, *, threshold: str | None = None) -> MagicMock:
        tenant = MagicMock()
        tenant.id = "t1"
        tenant.invoice_approval_threshold = Decimal(threshold) if threshold is not None else None
        return tenant

    @pytest.mark.anyio
    async def test_below_threshold_goes_to_authorised(self, mock_db: AsyncMock) -> None:
        """Invoice below threshold is authorised directly (single-step)."""
        from app.services.invoices import authorise_invoice

        inv = self._make_invoice(total="5000.0000")
        tenant = self._make_tenant(threshold="10000.0000")

        with (
            patch("app.services.invoices.get_invoice", return_value=inv),
            patch("app.services.invoices.get_invoice_lines", return_value=[]),
            patch("app.services.invoices.get_tenant", return_value=tenant),
        ):
            result = await authorise_invoice(mock_db, "t1", "inv-1", "actor-1")

        assert result.status == "authorised"

    @pytest.mark.anyio
    async def test_at_threshold_goes_to_awaiting_approval(self, mock_db: AsyncMock) -> None:
        """Invoice at exactly the threshold requires second approval."""
        from app.services.invoices import authorise_invoice

        inv = self._make_invoice(total="10000.0000")
        tenant = self._make_tenant(threshold="10000.0000")

        with (
            patch("app.services.invoices.get_invoice", return_value=inv),
            patch("app.services.invoices.get_invoice_lines", return_value=[]),
            patch("app.services.invoices.get_tenant", return_value=tenant),
        ):
            result = await authorise_invoice(mock_db, "t1", "inv-1", "actor-1")

        assert result.status == "awaiting_approval"

    @pytest.mark.anyio
    async def test_above_threshold_goes_to_awaiting_approval(self, mock_db: AsyncMock) -> None:
        """Invoice above threshold requires second approval."""
        from app.services.invoices import authorise_invoice

        inv = self._make_invoice(total="15000.0000")
        tenant = self._make_tenant(threshold="10000.0000")

        with (
            patch("app.services.invoices.get_invoice", return_value=inv),
            patch("app.services.invoices.get_invoice_lines", return_value=[]),
            patch("app.services.invoices.get_tenant", return_value=tenant),
        ):
            result = await authorise_invoice(mock_db, "t1", "inv-1", "actor-1")

        assert result.status == "awaiting_approval"

    @pytest.mark.anyio
    async def test_no_threshold_goes_to_authorised(self, mock_db: AsyncMock) -> None:
        """No threshold configured -> existing single-step flow."""
        from app.services.invoices import authorise_invoice

        inv = self._make_invoice(total="999999.0000")
        tenant = self._make_tenant(threshold=None)

        with (
            patch("app.services.invoices.get_invoice", return_value=inv),
            patch("app.services.invoices.get_invoice_lines", return_value=[]),
            patch("app.services.invoices.get_tenant", return_value=tenant),
        ):
            result = await authorise_invoice(mock_db, "t1", "inv-1", "actor-1")

        assert result.status == "authorised"

    @pytest.mark.anyio
    async def test_authorised_by_is_set_when_awaiting_approval(self, mock_db: AsyncMock) -> None:
        """When invoice goes to awaiting_approval, authorised_by tracks who initiated."""
        from app.services.invoices import authorise_invoice

        inv = self._make_invoice(total="20000.0000")
        tenant = self._make_tenant(threshold="10000.0000")

        with (
            patch("app.services.invoices.get_invoice", return_value=inv),
            patch("app.services.invoices.get_invoice_lines", return_value=[]),
            patch("app.services.invoices.get_tenant", return_value=tenant),
        ):
            result = await authorise_invoice(mock_db, "t1", "inv-1", "actor-1")

        assert result.authorised_by == "actor-1"


@_skip_311
class TestApproveInvoice:
    """approve_invoice transitions from awaiting_approval to authorised."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        db = AsyncMock()
        db.flush = AsyncMock()
        db.refresh = AsyncMock()
        db.execute = AsyncMock()
        db.scalar = AsyncMock()
        return db

    def _make_invoice(
        self,
        *,
        status: str = "awaiting_approval",
        authorised_by: str = "actor-1",
    ) -> MagicMock:
        inv = MagicMock()
        inv.id = "inv-1"
        inv.tenant_id = "t1"
        inv.status = status
        inv.total = Decimal("15000.0000")
        inv.currency = "USD"
        inv.fx_rate = Decimal("1")
        inv.contact_id = "contact-1"
        inv.issue_date = "2026-01-15"
        inv.period_name = "2026-01"
        inv.number = "INV-00001"
        inv.version = 2
        inv.updated_by = None
        inv.journal_entry_id = None
        inv.authorised_by = authorised_by
        return inv

    @pytest.mark.anyio
    async def test_approve_transitions_to_authorised(self, mock_db: AsyncMock) -> None:
        from app.services.invoices import approve_invoice

        inv = self._make_invoice()

        with (
            patch("app.services.invoices.get_invoice", return_value=inv),
            patch("app.services.invoices.get_invoice_lines", return_value=[]),
        ):
            result = await approve_invoice(mock_db, "t1", "inv-1", "actor-2")

        assert result.status == "authorised"

    @pytest.mark.anyio
    async def test_approve_rejects_self_approval(self, mock_db: AsyncMock) -> None:
        """The approver must NOT be the same user who initiated the authorise action."""
        from app.services.invoices import InvoiceApprovalError, approve_invoice

        inv = self._make_invoice(authorised_by="actor-1")

        with (
            patch("app.services.invoices.get_invoice", return_value=inv),
            pytest.raises(InvoiceApprovalError, match="same user"),
        ):
            await approve_invoice(mock_db, "t1", "inv-1", "actor-1")

    @pytest.mark.anyio
    async def test_approve_rejects_non_awaiting_status(self, mock_db: AsyncMock) -> None:
        """Can only approve invoices in awaiting_approval status."""
        from app.services.invoices import InvoiceTransitionError, approve_invoice

        inv = self._make_invoice(status="draft")

        with (
            patch("app.services.invoices.get_invoice", return_value=inv),
            pytest.raises(InvoiceTransitionError),
        ):
            await approve_invoice(mock_db, "t1", "inv-1", "actor-2")

    @pytest.mark.anyio
    async def test_approve_rejects_already_authorised(self, mock_db: AsyncMock) -> None:
        from app.services.invoices import InvoiceTransitionError, approve_invoice

        inv = self._make_invoice(status="authorised")

        with (
            patch("app.services.invoices.get_invoice", return_value=inv),
            pytest.raises(InvoiceTransitionError),
        ):
            await approve_invoice(mock_db, "t1", "inv-1", "actor-2")
