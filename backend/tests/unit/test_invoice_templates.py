"""Unit tests for invoice template and recurring invoice generation.

Tests the core logic of saving invoices as templates and generating
new invoices from templates, using in-memory SQLite.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
import sqlalchemy as sa
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.core.db import Base
from app.infra.models import (
    Account,
    Contact,
    Invoice,
    InvoiceLine,
    InvoiceTemplate,
    Tenant,
)
from app.services.invoice_templates import _advance_date

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def engine() -> sa.engine.Engine:
    eng = create_engine("sqlite:///:memory:", echo=False)

    @event.listens_for(eng, "connect")
    def _set_sqlite_pragma(dbapi_conn, connection_record):  # type: ignore[no-untyped-def]
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=OFF")
        cursor.close()

    from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler

    if not hasattr(SQLiteTypeCompiler, "visit_JSONB"):
        SQLiteTypeCompiler.visit_JSONB = lambda self, type_, **kw: "TEXT"  # type: ignore[attr-defined]
    if not hasattr(SQLiteTypeCompiler, "visit_UUID"):
        SQLiteTypeCompiler.visit_UUID = lambda self, type_, **kw: "VARCHAR(36)"  # type: ignore[attr-defined]
    if not hasattr(SQLiteTypeCompiler, "visit_TIMESTAMP"):
        SQLiteTypeCompiler.visit_TIMESTAMP = lambda self, type_, **kw: "TIMESTAMP"  # type: ignore[attr-defined]
    if not hasattr(SQLiteTypeCompiler, "visit_INET"):
        SQLiteTypeCompiler.visit_INET = lambda self, type_, **kw: "VARCHAR(45)"  # type: ignore[attr-defined]

    # Strip Postgres-specific server defaults before creating tables
    for table in Base.metadata.sorted_tables:
        for col in table.columns:
            if col.server_default is not None:
                sd_text = str(col.server_default.arg) if hasattr(col.server_default, "arg") else ""
                if "now()" in sd_text:
                    col.server_default = None

    Base.metadata.create_all(eng)
    return eng


@pytest.fixture()
def session(engine: sa.engine.Engine) -> Session:
    factory = sessionmaker(bind=engine)
    sess = factory()
    yield sess  # type: ignore[misc]
    sess.close()


@pytest.fixture()
def tenant(session: Session) -> Tenant:
    t = Tenant(
        id=str(uuid.uuid4()),
        name="Test Corp",
        legal_name="Test Corp Ltd",
        country="US",
        functional_currency="USD",
        fiscal_year_start_month=1,
        created_at=datetime.now(tz=UTC),
        updated_at=datetime.now(tz=UTC),
    )
    session.add(t)
    session.flush()
    return t


@pytest.fixture()
def contact(session: Session, tenant: Tenant) -> Contact:
    c = Contact(
        id=str(uuid.uuid4()),
        tenant_id=tenant.id,
        contact_type="customer",
        name="Acme Corp",
        currency="USD",
        created_at=datetime.now(tz=UTC),
        updated_at=datetime.now(tz=UTC),
    )
    session.add(c)
    session.flush()
    return c


@pytest.fixture()
def revenue_account(session: Session, tenant: Tenant) -> Account:
    acct = Account(
        id=str(uuid.uuid4()),
        tenant_id=tenant.id,
        code="4000",
        name="Sales Revenue",
        type="revenue",
        subtype="other",
        normal_balance="credit",
        is_active=True,
        is_system=False,
        is_control_account=False,
        created_at=datetime.now(tz=UTC),
        updated_at=datetime.now(tz=UTC),
    )
    session.add(acct)
    session.flush()
    return acct


# ---------------------------------------------------------------------------
# Tests: InvoiceTemplate model
# ---------------------------------------------------------------------------


class TestInvoiceTemplateModel:
    def test_create_template(
        self, session: Session, tenant: Tenant, contact: Contact, revenue_account: Account
    ) -> None:
        lines_json = [
            {
                "account_id": revenue_account.id,
                "description": "Monthly consulting",
                "quantity": "10",
                "unit_price": "150.00",
                "discount_pct": "0",
            }
        ]
        template = InvoiceTemplate(
            id=str(uuid.uuid4()),
            tenant_id=tenant.id,
            contact_id=contact.id,
            name="Monthly Consulting Invoice",
            currency="USD",
            lines_json=json.dumps(lines_json) if isinstance(lines_json, list) else lines_json,
            recurrence_frequency="monthly",
            next_generation_date=date(2026, 5, 1),
            is_active=True,
            created_at=datetime.now(tz=UTC),
            updated_at=datetime.now(tz=UTC),
        )
        session.add(template)
        session.flush()

        loaded = session.get(InvoiceTemplate, template.id)
        assert loaded is not None
        assert loaded.name == "Monthly Consulting Invoice"
        assert loaded.recurrence_frequency == "monthly"
        assert loaded.is_active is True
        assert loaded.contact_id == contact.id

    def test_template_with_no_recurrence(
        self, session: Session, tenant: Tenant, contact: Contact
    ) -> None:
        """A template without recurrence is valid (for manual one-off generation)."""
        template = InvoiceTemplate(
            id=str(uuid.uuid4()),
            tenant_id=tenant.id,
            contact_id=contact.id,
            name="One-off Template",
            currency="USD",
            lines_json="[]",
            recurrence_frequency=None,
            next_generation_date=None,
            is_active=True,
            created_at=datetime.now(tz=UTC),
            updated_at=datetime.now(tz=UTC),
        )
        session.add(template)
        session.flush()

        loaded = session.get(InvoiceTemplate, template.id)
        assert loaded is not None
        assert loaded.recurrence_frequency is None

    def test_deactivate_template(self, session: Session, tenant: Tenant, contact: Contact) -> None:
        template = InvoiceTemplate(
            id=str(uuid.uuid4()),
            tenant_id=tenant.id,
            contact_id=contact.id,
            name="Deactivated",
            currency="USD",
            lines_json="[]",
            is_active=True,
            created_at=datetime.now(tz=UTC),
            updated_at=datetime.now(tz=UTC),
        )
        session.add(template)
        session.flush()

        template.is_active = False
        session.flush()

        loaded = session.get(InvoiceTemplate, template.id)
        assert loaded is not None
        assert loaded.is_active is False


# ---------------------------------------------------------------------------
# Tests: Date advancement for recurrence
# ---------------------------------------------------------------------------


class TestDateAdvancement:
    def test_weekly_advance(self) -> None:
        d = date(2026, 4, 1)
        result = _advance_date(d, "weekly")
        assert result == date(2026, 4, 8)

    def test_monthly_advance(self) -> None:
        d = date(2026, 1, 15)
        result = _advance_date(d, "monthly")
        assert result == date(2026, 2, 15)

    def test_monthly_advance_end_of_month(self) -> None:
        d = date(2026, 1, 31)
        result = _advance_date(d, "monthly")
        # Feb doesn't have 31 days, dateutil handles this gracefully
        assert result.month == 2
        assert result.day == 28

    def test_quarterly_advance(self) -> None:
        d = date(2026, 1, 1)
        result = _advance_date(d, "quarterly")
        assert result == date(2026, 4, 1)

    def test_annually_advance(self) -> None:
        d = date(2026, 6, 15)
        result = _advance_date(d, "annually")
        assert result == date(2027, 6, 15)

    def test_unknown_frequency_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown frequency"):
            _advance_date(date(2026, 1, 1), "biweekly")


# ---------------------------------------------------------------------------
# Tests: Invoice-to-template conversion (model layer)
# ---------------------------------------------------------------------------


class TestSaveInvoiceAsTemplate:
    def test_invoice_lines_captured_in_template(
        self, session: Session, tenant: Tenant, contact: Contact, revenue_account: Account
    ) -> None:
        """Verify that saving an invoice as template preserves line item data."""
        inv = Invoice(
            id=str(uuid.uuid4()),
            tenant_id=tenant.id,
            number="INV-00001",
            status="authorised",
            contact_id=contact.id,
            issue_date=date(2026, 4, 1),
            currency="USD",
            fx_rate=Decimal("1"),
            subtotal=Decimal("1500"),
            tax_total=Decimal("0"),
            total=Decimal("1500"),
            amount_due=Decimal("1500"),
            functional_total=Decimal("1500"),
            created_at=datetime.now(tz=UTC),
            updated_at=datetime.now(tz=UTC),
        )
        session.add(inv)
        session.flush()

        inv_line = InvoiceLine(
            id=str(uuid.uuid4()),
            tenant_id=tenant.id,
            invoice_id=inv.id,
            line_no=1,
            account_id=revenue_account.id,
            description="Consulting services",
            quantity=Decimal("10"),
            unit_price=Decimal("150"),
            discount_pct=Decimal("0"),
            line_amount=Decimal("1500"),
            tax_amount=Decimal("0"),
        )
        session.add(inv_line)
        session.flush()

        # Simulate building lines_json from invoice lines
        lines_json = [
            {
                "account_id": inv_line.account_id,
                "description": inv_line.description,
                "quantity": str(inv_line.quantity),
                "unit_price": str(inv_line.unit_price),
                "discount_pct": str(inv_line.discount_pct),
            }
        ]

        template = InvoiceTemplate(
            id=str(uuid.uuid4()),
            tenant_id=tenant.id,
            contact_id=inv.contact_id,
            name="From INV-00001",
            currency=inv.currency,
            lines_json=json.dumps(lines_json),
            recurrence_frequency="monthly",
            next_generation_date=date(2026, 5, 1),
            is_active=True,
            created_at=datetime.now(tz=UTC),
            updated_at=datetime.now(tz=UTC),
        )
        session.add(template)
        session.flush()

        loaded = session.get(InvoiceTemplate, template.id)
        assert loaded is not None
        assert loaded.contact_id == contact.id
        loaded_lines = (
            json.loads(loaded.lines_json)
            if isinstance(loaded.lines_json, str)
            else loaded.lines_json
        )
        assert len(loaded_lines) == 1
        assert loaded_lines[0]["description"] == "Consulting services"
        assert loaded_lines[0]["quantity"] == "10"
        assert loaded_lines[0]["unit_price"] == "150"
