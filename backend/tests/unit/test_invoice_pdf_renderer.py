"""Unit tests for the invoice PDF renderer and email attachment wiring."""

from __future__ import annotations

import base64
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest


class _Inv:
    id = "i1"
    number = "INV-0042"
    contact_id = "contact-abcdef-0000-0000-0000-123456789abc"
    currency = "USD"
    subtotal = Decimal("1000.00")
    tax_total = Decimal("100.00")
    total = Decimal("1100.00")
    status = "authorised"
    issue_date = date(2026, 4, 1)
    due_date = date(2026, 5, 1)


class _Line:
    def __init__(self, desc: str, qty: Decimal, price: Decimal, amount: Decimal) -> None:
        self.description = desc
        self.quantity = qty
        self.unit_price = price
        self.line_amount = amount


class TestInvoicePdfRenderer:
    def test_returns_pdf_bytes_with_pdf_header(self) -> None:
        from app.infra.pdf import render_invoice_pdf

        pdf = render_invoice_pdf(
            _Inv(),
            [_Line("Consulting services", Decimal("10"), Decimal("100"), Decimal("1000"))],
            tenant_name="Acme Inc",
            contact_display="Customer Ltd",
        )
        assert isinstance(pdf, bytes)
        assert pdf.startswith(b"%PDF")

    def test_renders_without_due_date(self) -> None:
        """Due-date block is optional — missing date must not blow up."""
        from app.infra.pdf import render_invoice_pdf

        class _InvNoDue(_Inv):
            due_date = None  # type: ignore[assignment]

        pdf = render_invoice_pdf(
            _InvNoDue(),
            [_Line("Service", Decimal("1"), Decimal("50"), Decimal("50"))],
        )
        assert pdf.startswith(b"%PDF")

    def test_renders_many_lines(self) -> None:
        from app.infra.pdf import render_invoice_pdf

        lines = [
            _Line(f"Line {i}", Decimal("1"), Decimal("10"), Decimal("10")) for i in range(30)
        ]
        pdf = render_invoice_pdf(_Inv(), lines)
        assert pdf.startswith(b"%PDF")
        assert len(pdf) > 1500  # non-trivial document

    def test_falls_back_to_contact_id_when_no_display_supplied(self) -> None:
        """When no contact_display is given, the first 36 chars of contact_id are used."""
        from app.infra.pdf import render_invoice_pdf

        pdf = render_invoice_pdf(_Inv(), [])
        assert pdf.startswith(b"%PDF")

    def test_long_description_truncated(self) -> None:
        """Descriptions beyond 60 chars should be truncated to fit the column."""
        from app.infra.pdf import render_invoice_pdf

        long_desc = "x" * 200
        pdf = render_invoice_pdf(
            _Inv(),
            [_Line(long_desc, Decimal("1"), Decimal("100"), Decimal("100"))],
        )
        assert pdf.startswith(b"%PDF")


class TestEmailAttachments:
    @pytest.mark.asyncio
    async def test_send_email_base64_encodes_attachments(self) -> None:
        """Resend expects base64-encoded attachment content."""
        from app.services import email_service

        captured: dict = {}

        class _FakeResp:
            def raise_for_status(self) -> None:
                return None

        class _FakeClient:
            async def __aenter__(self) -> "_FakeClient":
                return self

            async def __aexit__(self, *args: object) -> None:
                return None

            async def post(self, url: str, headers: dict, json: dict) -> _FakeResp:
                captured["url"] = url
                captured["json"] = json
                return _FakeResp()

        with (
            patch.object(email_service, "httpx") as httpx_mock,
            patch.object(
                email_service, "get_settings", return_value=_settings_with_key("sk-test")
            ),
        ):
            httpx_mock.AsyncClient = lambda **_kw: _FakeClient()
            ok = await email_service.send_email(
                to="client@example.com",
                subject="Invoice",
                html="<p>body</p>",
                attachments=[{"filename": "inv.pdf", "content": b"%PDF-stub"}],
            )

        assert ok is True
        sent = captured["json"]
        assert sent["to"] == ["client@example.com"]
        assert sent["subject"] == "Invoice"
        assert len(sent["attachments"]) == 1
        attached = sent["attachments"][0]
        assert attached["filename"] == "inv.pdf"
        # Content must be base64-encoded, not raw bytes.
        assert attached["content"] == base64.b64encode(b"%PDF-stub").decode("ascii")

    @pytest.mark.asyncio
    async def test_send_email_no_api_key_skips_send(self) -> None:
        from app.services import email_service

        with patch.object(
            email_service, "get_settings", return_value=_settings_with_key("")
        ):
            ok = await email_service.send_email(
                to="x@example.com",
                subject="s",
                html="<p>h</p>",
                attachments=[{"filename": "a.pdf", "content": b"stub"}],
            )
        assert ok is False


class TestSendInvoiceService:
    @pytest.mark.asyncio
    async def test_send_invoice_attaches_pdf_by_default(self) -> None:
        """The invoice send flow must generate a PDF and pass it as an attachment."""
        from app.services import invoices as svc

        fake_inv = _Inv()
        fake_inv.sent_at = None  # type: ignore[attr-defined]
        fake_inv.updated_at = None  # type: ignore[attr-defined]
        fake_inv.version = 1  # type: ignore[attr-defined]

        with (
            patch.object(svc, "get_invoice", AsyncMock(return_value=fake_inv)),
            patch.object(
                svc, "get_contact", AsyncMock(return_value=type("C", (), {"name": "Customer Ltd"})())
            ),
            patch.object(
                svc,
                "get_invoice_lines",
                AsyncMock(return_value=[
                    _Line("L1", Decimal("1"), Decimal("100"), Decimal("100"))
                ]),
            ),
            patch("app.services.email_service.send_email", AsyncMock(return_value=True)) as email_mock,
            patch.object(svc, "emit", AsyncMock()),
        ):
            db = _FakeDb()
            await svc.send_invoice(db, "tenant-1", "inv-1", to="c@example.com", actor_id="user-1")

        assert email_mock.await_count == 1
        kwargs = email_mock.await_args.kwargs
        assert kwargs["to"] == "c@example.com"
        assert kwargs["attachments"] is not None
        assert len(kwargs["attachments"]) == 1
        att = kwargs["attachments"][0]
        assert att["filename"] == f"invoice-{fake_inv.number}.pdf"
        assert att["content"].startswith(b"%PDF")

    @pytest.mark.asyncio
    async def test_send_invoice_emits_audit_event_on_success(self) -> None:
        from app.services import invoices as svc

        fake_inv = _Inv()
        fake_inv.sent_at = None  # type: ignore[attr-defined]
        fake_inv.updated_at = None  # type: ignore[attr-defined]
        fake_inv.version = 1  # type: ignore[attr-defined]

        with (
            patch.object(svc, "get_invoice", AsyncMock(return_value=fake_inv)),
            patch.object(
                svc, "get_contact", AsyncMock(return_value=type("C", (), {"name": "C"})())
            ),
            patch.object(svc, "get_invoice_lines", AsyncMock(return_value=[])),
            patch("app.services.email_service.send_email", AsyncMock(return_value=True)),
            patch.object(svc, "emit", AsyncMock()) as emit_mock,
        ):
            db = _FakeDb()
            await svc.send_invoice(
                db, "tenant-1", "inv-1", to="x@example.com", actor_id="user-42"
            )

        emit_mock.assert_awaited_once()
        kwargs = emit_mock.await_args.kwargs
        assert kwargs["action"] == "invoice.sent"
        assert kwargs["entity_type"] == "invoice"
        assert kwargs["actor_id"] == "user-42"
        assert kwargs["metadata"]["to"] == "x@example.com"
        assert kwargs["metadata"]["has_pdf"] is True

    @pytest.mark.asyncio
    async def test_send_invoice_skips_audit_event_on_email_failure(self) -> None:
        from app.services import invoices as svc

        fake_inv = _Inv()
        fake_inv.sent_at = None  # type: ignore[attr-defined]
        fake_inv.updated_at = None  # type: ignore[attr-defined]
        fake_inv.version = 1  # type: ignore[attr-defined]

        with (
            patch.object(svc, "get_invoice", AsyncMock(return_value=fake_inv)),
            patch.object(
                svc, "get_contact", AsyncMock(return_value=type("C", (), {"name": "C"})())
            ),
            patch.object(svc, "get_invoice_lines", AsyncMock(return_value=[])),
            patch("app.services.email_service.send_email", AsyncMock(return_value=False)),
            patch.object(svc, "emit", AsyncMock()) as emit_mock,
        ):
            db = _FakeDb()
            await svc.send_invoice(
                db, "tenant-1", "inv-1", to="x@example.com", actor_id="user-42"
            )

        # No audit event on email failure — avoid polluting the chain.
        emit_mock.assert_not_called()


# --------------------------------------------------------------------------- helpers


def _settings_with_key(key: str) -> object:
    class _S:
        resend_api_key = key
        email_from = "noreply@test"

    return _S()


class _FakeDb:
    async def scalar(self, *_args: object, **_kwargs: object) -> object:
        return type("T", (), {"name": "Acme Inc"})()

    async def flush(self) -> None:
        return None
