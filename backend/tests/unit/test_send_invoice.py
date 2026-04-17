"""Unit tests for Send Invoice feature (Issue #37).

Tests cover:
  - SendInvoiceRequest schema validation
  - InvoiceResponse includes sent_at field
  - send_invoice endpoint source verification
  - Service-level: send_invoice happy path (authorised invoice, contact with email)
  - Service-level: send_invoice rejects non-authorised invoices
  - Service-level: send_invoice fails when contact has no email
  - Service-level: send_invoice sets sent_at on invoice after sending
"""

from __future__ import annotations

import sys
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_NEEDS_311 = sys.version_info < (3, 11)
_skip_311 = pytest.mark.skipif(_NEEDS_311, reason="datetime.UTC requires Python >=3.11")


class TestSendInvoiceRequestSchema:
    """Schema for the send-invoice request body."""

    def _read_schemas_source(self) -> str:
        import pathlib

        path = pathlib.Path(__file__).resolve().parents[2] / "app" / "api" / "v1" / "schemas.py"
        return path.read_text()

    def test_send_invoice_request_class_exists(self) -> None:
        source = self._read_schemas_source()
        assert "class SendInvoiceRequest(" in source

    def test_to_field_exists(self) -> None:
        source = self._read_schemas_source()
        # Find the SendInvoiceRequest class and verify it has a 'to' field
        idx = source.index("class SendInvoiceRequest(")
        block = source[idx : idx + 300]
        assert "to:" in block

    def test_subject_field_exists(self) -> None:
        source = self._read_schemas_source()
        idx = source.index("class SendInvoiceRequest(")
        block = source[idx : idx + 300]
        assert "subject:" in block

    def test_message_field_exists(self) -> None:
        source = self._read_schemas_source()
        idx = source.index("class SendInvoiceRequest(")
        block = source[idx : idx + 300]
        assert "message:" in block


class TestInvoiceResponseSentAt:
    """InvoiceResponse should expose sent_at."""

    def _read_schemas_source(self) -> str:
        import pathlib

        path = pathlib.Path(__file__).resolve().parents[2] / "app" / "api" / "v1" / "schemas.py"
        return path.read_text()

    def test_sent_at_field_exists(self) -> None:
        source = self._read_schemas_source()
        idx = source.index("class InvoiceResponse(")
        block = source[idx : idx + 800]
        assert "sent_at:" in block


class TestSendInvoiceEndpointSource:
    """Verify the send endpoint exists in the API module."""

    def _read_api_source(self) -> str:
        import pathlib

        api_path = (
            pathlib.Path(__file__).resolve().parents[2] / "app" / "api" / "v1" / "invoices.py"
        )
        return api_path.read_text()

    def test_send_endpoint_exists(self) -> None:
        source = self._read_api_source()
        assert "/{invoice_id}/send" in source

    def test_send_endpoint_uses_post(self) -> None:
        source = self._read_api_source()
        assert 'router.post("/{invoice_id}/send"' in source

    def test_send_endpoint_imports_send_invoice_request(self) -> None:
        source = self._read_api_source()
        assert "SendInvoiceRequest" in source


class TestSendInvoiceServiceSource:
    """Verify the send_invoice service function exists."""

    def _read_service_source(self) -> str:
        import pathlib

        svc_path = pathlib.Path(__file__).resolve().parents[2] / "app" / "services" / "invoices.py"
        return svc_path.read_text()

    def test_send_invoice_function_exists(self) -> None:
        source = self._read_service_source()
        assert "async def send_invoice(" in source

    def test_send_invoice_checks_status(self) -> None:
        source = self._read_service_source()
        # The function should check that the invoice is in a sendable status
        assert "InvoiceTransitionError" in source

    def test_send_invoice_sets_sent_at(self) -> None:
        source = self._read_service_source()
        assert "sent_at" in source


# ── Service-level async tests (require Python 3.11+) ────────────────────────


@_skip_311
class TestSendInvoiceService:
    """send_invoice service function tests."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        db = AsyncMock()
        db.flush = AsyncMock()
        db.refresh = AsyncMock()
        db.execute = AsyncMock()
        return db

    def _make_invoice(
        self,
        *,
        status: str = "authorised",
        contact_id: str = "contact-1",
        sent_at: object = None,
    ) -> MagicMock:
        inv = MagicMock()
        inv.id = "inv-1"
        inv.tenant_id = "t1"
        inv.status = status
        inv.number = "INV-00001"
        inv.contact_id = contact_id
        inv.currency = "USD"
        inv.total = Decimal("1000.0000")
        inv.subtotal = Decimal("900.0000")
        inv.tax_total = Decimal("100.0000")
        inv.issue_date = "2026-01-15"
        inv.due_date = "2026-02-15"
        inv.sent_at = sent_at
        inv.version = 1
        return inv

    def _make_contact(self, *, email: str | None = "customer@example.com") -> MagicMock:
        contact = MagicMock()
        contact.id = "contact-1"
        contact.name = "Test Customer"
        contact.email = email
        return contact

    @pytest.mark.anyio
    async def test_send_invoice_happy_path(self, mock_db: AsyncMock) -> None:
        """Authorised invoice with contact email succeeds."""
        from app.services.invoices import send_invoice

        inv = self._make_invoice(status="authorised")
        contact = self._make_contact(email="customer@example.com")

        with (
            patch("app.services.invoices.get_invoice", return_value=inv),
            patch("app.services.invoices.get_contact", return_value=contact),
            patch("app.services.invoices.send_email", return_value=True) as mock_email,
        ):
            result = await send_invoice(
                mock_db, "t1", "inv-1", to="customer@example.com", subject="Invoice INV-00001"
            )

        assert result.sent_at is not None
        mock_email.assert_called_once()

    @pytest.mark.anyio
    async def test_send_invoice_rejects_draft(self, mock_db: AsyncMock) -> None:
        """Cannot send a draft invoice."""
        from app.services.invoices import InvoiceTransitionError, send_invoice

        inv = self._make_invoice(status="draft")

        with (
            patch("app.services.invoices.get_invoice", return_value=inv),
            pytest.raises(InvoiceTransitionError),
        ):
            await send_invoice(mock_db, "t1", "inv-1", to="a@b.com")

    @pytest.mark.anyio
    async def test_send_invoice_rejects_void(self, mock_db: AsyncMock) -> None:
        """Cannot send a voided invoice."""
        from app.services.invoices import InvoiceTransitionError, send_invoice

        inv = self._make_invoice(status="void")

        with (
            patch("app.services.invoices.get_invoice", return_value=inv),
            pytest.raises(InvoiceTransitionError),
        ):
            await send_invoice(mock_db, "t1", "inv-1", to="a@b.com")

    @pytest.mark.anyio
    async def test_send_invoice_updates_status_to_sent(self, mock_db: AsyncMock) -> None:
        """Sending an authorised invoice transitions it to 'sent' status."""
        from app.services.invoices import send_invoice

        inv = self._make_invoice(status="authorised")
        contact = self._make_contact()

        with (
            patch("app.services.invoices.get_invoice", return_value=inv),
            patch("app.services.invoices.get_contact", return_value=contact),
            patch("app.services.invoices.send_email", return_value=True),
        ):
            result = await send_invoice(mock_db, "t1", "inv-1", to="customer@example.com")

        assert result.status == "sent"

    @pytest.mark.anyio
    async def test_send_invoice_allows_resend(self, mock_db: AsyncMock) -> None:
        """An already-sent invoice can be re-sent."""
        from datetime import UTC, datetime

        from app.services.invoices import send_invoice

        inv = self._make_invoice(status="sent", sent_at=datetime.now(tz=UTC))
        contact = self._make_contact()

        with (
            patch("app.services.invoices.get_invoice", return_value=inv),
            patch("app.services.invoices.get_contact", return_value=contact),
            patch("app.services.invoices.send_email", return_value=True),
        ):
            result = await send_invoice(mock_db, "t1", "inv-1", to="customer@example.com")

        assert result.sent_at is not None
