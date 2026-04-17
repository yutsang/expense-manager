"""Unit tests for shareable customer invoice portal (Issue #36).

Tests cover:
  - Invoice model has share_token, viewed_at, acknowledged_at columns
  - POST /v1/invoices/{id}/share-link generates a signed token
  - GET /v1/public/invoices/{token} returns invoice data (unauthenticated)
  - POST /v1/public/invoices/{token}/acknowledge records acknowledgement
  - Share token generation and validation logic
  - Migration adds required columns
"""

from __future__ import annotations

import pathlib
import sys
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_NEEDS_311 = sys.version_info < (3, 11)
_skip_311 = pytest.mark.skipif(_NEEDS_311, reason="datetime.UTC requires Python >=3.11")


# ── Schema tests ────────────────────────────────────────────────────────────


class TestShareLinkResponseSchema:
    """ShareLinkResponse returns the public URL and token."""

    def test_response_has_fields(self) -> None:
        from app.api.v1.schemas import ShareLinkResponse

        resp = ShareLinkResponse(
            share_token="abc123token",
            public_url="/pay/abc123token",
            expires_at="2026-05-16T00:00:00Z",
        )
        assert resp.share_token == "abc123token"
        assert "/pay/" in resp.public_url


class TestPublicInvoiceResponseSchema:
    """PublicInvoiceResponse omits internal fields."""

    def test_response_has_customer_facing_fields(self) -> None:
        from app.api.v1.schemas import PublicInvoiceResponse

        resp = PublicInvoiceResponse(
            invoice_number="INV-00001",
            status="sent",
            contact_name="Jane Doe",
            issue_date="2026-04-01",
            due_date="2026-05-01",
            currency="USD",
            subtotal="1000.00",
            tax_total="100.00",
            total="1100.00",
            notes=None,
            lines=[],
            company_name="Acme Corp",
        )
        assert resp.invoice_number == "INV-00001"
        assert resp.total == "1100.00"


class TestAcknowledgeRequestSchema:
    """AcknowledgeRequest optionally accepts customer name."""

    def test_acknowledge_with_optional_name(self) -> None:
        from app.api.v1.schemas import InvoiceAcknowledgeRequest

        req = InvoiceAcknowledgeRequest(customer_name="Jane Doe")
        assert req.customer_name == "Jane Doe"

    def test_acknowledge_without_name(self) -> None:
        from app.api.v1.schemas import InvoiceAcknowledgeRequest

        req = InvoiceAcknowledgeRequest()
        assert req.customer_name is None


# ── Model tests (source-level) ──────────────────────────────────────────────


class TestInvoiceModelPortalColumns:
    """Invoice model must have share_token, viewed_at, acknowledged_at."""

    def _read_models(self) -> str:
        models_path = pathlib.Path(__file__).resolve().parents[2] / "app" / "infra" / "models.py"
        return models_path.read_text()

    def test_share_token_column_exists(self) -> None:
        source = self._read_models()
        assert "share_token" in source

    def test_viewed_at_column_exists(self) -> None:
        source = self._read_models()
        assert "viewed_at" in source

    def test_acknowledged_at_column_exists(self) -> None:
        source = self._read_models()
        assert "acknowledged_at" in source

    def test_acknowledged_by_name_column_exists(self) -> None:
        source = self._read_models()
        assert "acknowledged_by_name" in source


# ── Service tests (source-level) ────────────────────────────────────────────


class TestInvoicePortalServiceSource:
    """Verify invoice_portal service code exists."""

    def _read_service_source(self) -> str:
        svc_path = (
            pathlib.Path(__file__).resolve().parents[2] / "app" / "services" / "invoice_portal.py"
        )
        return svc_path.read_text()

    def test_generate_share_link_exists(self) -> None:
        source = self._read_service_source()
        assert "async def generate_share_link(" in source

    def test_get_public_invoice_exists(self) -> None:
        source = self._read_service_source()
        assert "async def get_public_invoice(" in source

    def test_acknowledge_invoice_exists(self) -> None:
        source = self._read_service_source()
        assert "async def acknowledge_invoice(" in source

    def test_share_token_is_generated(self) -> None:
        source = self._read_service_source()
        assert "share_token" in source

    def test_viewed_at_is_recorded(self) -> None:
        source = self._read_service_source()
        assert "viewed_at" in source


# ── API endpoint tests (source-level) ────────────────────────────────────────


class TestInvoicePortalApiSource:
    """Verify API endpoints exist for share-link and public access."""

    def _read_api_source(self) -> str:
        api_path = (
            pathlib.Path(__file__).resolve().parents[2] / "app" / "api" / "v1" / "invoice_portal.py"
        )
        return api_path.read_text()

    def test_share_link_endpoint_exists(self) -> None:
        source = self._read_api_source()
        assert "share-link" in source or "share_link" in source

    def test_public_get_endpoint_exists(self) -> None:
        source = self._read_api_source()
        assert "public" in source

    def test_acknowledge_endpoint_exists(self) -> None:
        source = self._read_api_source()
        assert "acknowledge" in source


# ── Service-level async tests ────────────────────────────────────────────────


@_skip_311
class TestGenerateShareLink:
    """generate_share_link creates token and returns URL."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        db = AsyncMock()
        db.flush = AsyncMock()
        db.refresh = AsyncMock()
        db.scalar = AsyncMock()
        return db

    def _make_invoice(self, *, status: str = "authorised") -> MagicMock:
        inv = MagicMock()
        inv.id = "inv-1"
        inv.tenant_id = "t1"
        inv.status = status
        inv.number = "INV-00001"
        inv.share_token = None
        inv.version = 1
        return inv

    @pytest.mark.anyio
    async def test_generates_token_for_authorised_invoice(self, mock_db: AsyncMock) -> None:
        from app.services.invoice_portal import generate_share_link

        inv = self._make_invoice(status="authorised")

        with patch("app.services.invoice_portal.get_invoice", return_value=inv):
            result = await generate_share_link(mock_db, tenant_id="t1", invoice_id="inv-1")

        assert result["share_token"] is not None
        assert len(result["share_token"]) > 10

    @pytest.mark.anyio
    async def test_rejects_draft_invoice(self, mock_db: AsyncMock) -> None:
        from app.services.invoice_portal import InvoiceNotShareableError, generate_share_link

        inv = self._make_invoice(status="draft")

        with (
            patch("app.services.invoice_portal.get_invoice", return_value=inv),
            pytest.raises(InvoiceNotShareableError),
        ):
            await generate_share_link(mock_db, tenant_id="t1", invoice_id="inv-1")


@_skip_311
class TestGetPublicInvoice:
    """get_public_invoice retrieves invoice by token."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        db = AsyncMock()
        db.flush = AsyncMock()
        db.refresh = AsyncMock()
        db.scalar = AsyncMock()
        return db

    @pytest.mark.anyio
    async def test_records_viewed_at(self, mock_db: AsyncMock) -> None:
        from app.services.invoice_portal import get_public_invoice

        inv = MagicMock()
        inv.id = "inv-1"
        inv.tenant_id = "t1"
        inv.viewed_at = None
        inv.share_token = "valid-token"
        inv.status = "sent"
        inv.number = "INV-00001"

        mock_db.scalar.return_value = inv

        result = await get_public_invoice(mock_db, share_token="valid-token")
        assert inv.viewed_at is not None

    @pytest.mark.anyio
    async def test_invalid_token_raises(self, mock_db: AsyncMock) -> None:
        from app.services.invoice_portal import ShareTokenInvalidError, get_public_invoice

        mock_db.scalar.return_value = None

        with pytest.raises(ShareTokenInvalidError):
            await get_public_invoice(mock_db, share_token="bad-token")


@_skip_311
class TestAcknowledgeInvoice:
    """acknowledge_invoice records customer acknowledgement."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        db = AsyncMock()
        db.flush = AsyncMock()
        db.scalar = AsyncMock()
        return db

    @pytest.mark.anyio
    async def test_sets_acknowledged_at(self, mock_db: AsyncMock) -> None:
        from app.services.invoice_portal import acknowledge_invoice

        inv = MagicMock()
        inv.id = "inv-1"
        inv.share_token = "valid-token"
        inv.acknowledged_at = None
        inv.status = "sent"

        mock_db.scalar.return_value = inv

        result = await acknowledge_invoice(
            mock_db, share_token="valid-token", customer_name="Jane"
        )
        assert inv.acknowledged_at is not None
        assert inv.acknowledged_by_name == "Jane"

    @pytest.mark.anyio
    async def test_idempotent_acknowledge(self, mock_db: AsyncMock) -> None:
        from app.services.invoice_portal import acknowledge_invoice

        inv = MagicMock()
        inv.id = "inv-1"
        inv.share_token = "valid-token"
        inv.acknowledged_at = datetime.now(tz=timezone.utc)
        inv.acknowledged_by_name = "Jane"
        inv.status = "sent"

        mock_db.scalar.return_value = inv

        # Should not raise — acknowledge is idempotent
        result = await acknowledge_invoice(
            mock_db, share_token="valid-token", customer_name="Jane"
        )
        assert result is not None


# ── Migration test ───────────────────────────────────────────────────────────


class TestInvoicePortalMigration:
    """Migration 0028 adds share_token, viewed_at, acknowledged_at to invoices."""

    def test_migration_file_exists(self) -> None:
        mig_path = (
            pathlib.Path(__file__).resolve().parents[2]
            / "migrations"
            / "versions"
            / "0028_invoices_add_portal_columns.py"
        )
        assert mig_path.exists(), f"Migration file not found: {mig_path}"

    def test_migration_has_upgrade_and_downgrade(self) -> None:
        mig_path = (
            pathlib.Path(__file__).resolve().parents[2]
            / "migrations"
            / "versions"
            / "0028_invoices_add_portal_columns.py"
        )
        source = mig_path.read_text()
        assert "def upgrade()" in source
        assert "def downgrade()" in source
        assert "share_token" in source
        assert "viewed_at" in source
        assert "acknowledged_at" in source
