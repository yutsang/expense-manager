"""Tests for Issue #4: Date columns should use sa.Date() not String(10).

Verifies that the Invoice, Bill, and Payment ORM models use proper
Date column types for date fields, and that the Pydantic schemas
accept datetime.date objects.
"""

from __future__ import annotations

import datetime
from decimal import Decimal

import pytest
import sqlalchemy as sa

from app.infra.models import Bill, Invoice, Payment


class TestInvoiceDateColumns:
    """Invoice.issue_date and Invoice.due_date should be Date type."""

    def test_issue_date_column_is_date_type(self) -> None:
        col = Invoice.__table__.c.issue_date
        assert isinstance(col.type, sa.Date), (
            f"Invoice.issue_date should be sa.Date(), got {col.type}"
        )

    def test_due_date_column_is_date_type(self) -> None:
        col = Invoice.__table__.c.due_date
        assert isinstance(col.type, sa.Date), (
            f"Invoice.due_date should be sa.Date(), got {col.type}"
        )


class TestBillDateColumns:
    """Bill.issue_date and Bill.due_date should be Date type."""

    def test_issue_date_column_is_date_type(self) -> None:
        col = Bill.__table__.c.issue_date
        assert isinstance(col.type, sa.Date), (
            f"Bill.issue_date should be sa.Date(), got {col.type}"
        )

    def test_due_date_column_is_date_type(self) -> None:
        col = Bill.__table__.c.due_date
        assert isinstance(col.type, sa.Date), (
            f"Bill.due_date should be sa.Date(), got {col.type}"
        )


class TestPaymentDateColumn:
    """Payment.payment_date should be Date type."""

    def test_payment_date_column_is_date_type(self) -> None:
        col = Payment.__table__.c.payment_date
        assert isinstance(col.type, sa.Date), (
            f"Payment.payment_date should be sa.Date(), got {col.type}"
        )


class TestPydanticSchemaDateTypes:
    """Pydantic response schemas should use date or str for date fields."""

    def test_invoice_response_issue_date_accepts_date(self) -> None:
        from app.api.v1.schemas import InvoiceResponse

        # Should accept a date object (converted to str for the response)
        data = {
            "id": "abc",
            "number": "INV-001",
            "status": "draft",
            "authorised_by": None,
            "contact_id": "c1",
            "issue_date": datetime.date(2025, 1, 15),
            "due_date": datetime.date(2025, 2, 15),
            "period_name": "2025-01",
            "reference": None,
            "currency": "USD",
            "fx_rate": "1",
            "subtotal": "100.00",
            "tax_total": "0.00",
            "total": "100.00",
            "amount_due": "100.00",
            "functional_total": "100.00",
            "journal_entry_id": None,
            "credit_note_for_id": None,
            "notes": None,
            "sent_at": None,
            "last_reminder_sent_at": None,
            "reminder_count": 0,
            "created_at": datetime.datetime(2025, 1, 1, tzinfo=datetime.timezone.utc),
            "updated_at": datetime.datetime(2025, 1, 1, tzinfo=datetime.timezone.utc),
            "lines": [],
        }
        resp = InvoiceResponse.model_validate(data)
        # The issue_date should be represented as a string in the response
        assert "2025-01-15" in str(resp.issue_date)

    def test_bill_response_issue_date_accepts_date(self) -> None:
        from app.api.v1.schemas import BillResponse

        data = {
            "id": "abc",
            "number": "BILL-001",
            "status": "draft",
            "contact_id": "c1",
            "supplier_reference": None,
            "issue_date": datetime.date(2025, 1, 15),
            "due_date": None,
            "period_name": None,
            "currency": "USD",
            "fx_rate": "1",
            "subtotal": "100.00",
            "tax_total": "0.00",
            "total": "100.00",
            "amount_due": "100.00",
            "functional_total": "100.00",
            "journal_entry_id": None,
            "notes": None,
            "approved_by": None,
            "approved_at": None,
            "created_at": datetime.datetime(2025, 1, 1, tzinfo=datetime.timezone.utc),
            "updated_at": datetime.datetime(2025, 1, 1, tzinfo=datetime.timezone.utc),
            "lines": [],
        }
        resp = BillResponse.model_validate(data)
        assert "2025-01-15" in str(resp.issue_date)

    def test_payment_response_payment_date_accepts_date(self) -> None:
        from app.api.v1.schemas import PaymentResponse

        data = {
            "id": "abc",
            "number": "PAY-001",
            "payment_type": "received",
            "contact_id": "c1",
            "amount": "500.00",
            "currency": "USD",
            "fx_rate": "1",
            "payment_date": datetime.date(2025, 3, 1),
            "reference": None,
            "status": "pending",
            "idempotency_key": None,
            "created_at": datetime.datetime(2025, 1, 1, tzinfo=datetime.timezone.utc),
            "updated_at": datetime.datetime(2025, 1, 1, tzinfo=datetime.timezone.utc),
        }
        resp = PaymentResponse.model_validate(data)
        assert "2025-03-01" in str(resp.payment_date)


class TestMigrationExists:
    """Verify a migration file exists for the date column change."""

    def test_migration_file_exists(self) -> None:
        import pathlib

        migrations_dir = pathlib.Path(__file__).resolve().parents[2] / "migrations" / "versions"
        migration_files = list(migrations_dir.glob("0032_*.py"))
        assert len(migration_files) == 1, (
            f"Expected exactly one 0032_* migration file for date columns, "
            f"found {len(migration_files)}"
        )

    def test_migration_has_downgrade(self) -> None:
        import pathlib

        migrations_dir = pathlib.Path(__file__).resolve().parents[2] / "migrations" / "versions"
        migration_files = list(migrations_dir.glob("0032_*.py"))
        assert migration_files, "No 0032_* migration file found"
        content = migration_files[0].read_text()
        assert "def downgrade()" in content, "Migration must have a downgrade() function"
        assert "def upgrade()" in content, "Migration must have an upgrade() function"
