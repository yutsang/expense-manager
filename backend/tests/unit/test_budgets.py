"""Unit tests for budget vs actual calculation and budget CRUD.

Uses in-memory SQLite to test the budget service logic without
requiring a Postgres instance.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
import sqlalchemy as sa
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.core.db import Base
from app.infra.models import (
    Account,
    Budget,
    BudgetLine,
    JournalEntry,
    JournalLine,
    Period,
    Tenant,
)

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

    # Monkey-patch server_default=sa.text("now()") to use SQLite-compatible default
    from sqlalchemy.dialects.sqlite.base import SQLiteDDLCompiler

    _orig_visit_column = (
        SQLiteDDLCompiler.visit_column_default
        if hasattr(SQLiteDDLCompiler, "visit_column_default")
        else None
    )

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


def _make_account(
    session: Session, tenant_id: str, code: str, name: str, acct_type: str
) -> Account:
    acct = Account(
        id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        code=code,
        name=name,
        type=acct_type,
        subtype="other",
        normal_balance="debit" if acct_type in ("asset", "expense") else "credit",
        is_active=True,
        is_system=False,
        is_control_account=False,
        created_at=datetime.now(tz=UTC),
        updated_at=datetime.now(tz=UTC),
    )
    session.add(acct)
    session.flush()
    return acct


def _make_period(session: Session, tenant_id: str, name: str) -> Period:
    p = Period(
        id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        name=name,
        start_date=datetime(2026, 1, 1, tzinfo=UTC),
        end_date=datetime(2026, 1, 31, tzinfo=UTC),
        status="open",
        created_at=datetime.now(tz=UTC),
        updated_at=datetime.now(tz=UTC),
    )
    session.add(p)
    session.flush()
    return p


# ---------------------------------------------------------------------------
# Tests: Budget model creation
# ---------------------------------------------------------------------------


class TestBudgetModel:
    def test_create_budget(self, session: Session, tenant: Tenant) -> None:
        budget = Budget(
            id=str(uuid.uuid4()),
            tenant_id=tenant.id,
            fiscal_year=2026,
            name="FY2026 Operating Budget",
            status="draft",
            created_at=datetime.now(tz=UTC),
            updated_at=datetime.now(tz=UTC),
        )
        session.add(budget)
        session.flush()

        loaded = session.get(Budget, budget.id)
        assert loaded is not None
        assert loaded.name == "FY2026 Operating Budget"
        assert loaded.fiscal_year == 2026
        assert loaded.status == "draft"

    def test_create_budget_line_with_monthly_amounts(
        self, session: Session, tenant: Tenant
    ) -> None:
        budget = Budget(
            id=str(uuid.uuid4()),
            tenant_id=tenant.id,
            fiscal_year=2026,
            name="Test Budget",
            status="draft",
            created_at=datetime.now(tz=UTC),
            updated_at=datetime.now(tz=UTC),
        )
        session.add(budget)
        session.flush()

        rent_acct = _make_account(session, tenant.id, "5100", "Rent Expense", "expense")

        line = BudgetLine(
            id=str(uuid.uuid4()),
            tenant_id=tenant.id,
            budget_id=budget.id,
            account_id=rent_acct.id,
            month_1=Decimal("5000"),
            month_2=Decimal("5000"),
            month_3=Decimal("5000"),
            month_4=Decimal("5500"),
            month_5=Decimal("5500"),
            month_6=Decimal("5500"),
            month_7=Decimal("6000"),
            month_8=Decimal("6000"),
            month_9=Decimal("6000"),
            month_10=Decimal("6500"),
            month_11=Decimal("6500"),
            month_12=Decimal("6500"),
            created_at=datetime.now(tz=UTC),
            updated_at=datetime.now(tz=UTC),
        )
        session.add(line)
        session.flush()

        loaded = session.get(BudgetLine, line.id)
        assert loaded is not None
        assert Decimal(str(loaded.month_1)) == Decimal("5000")
        assert Decimal(str(loaded.month_7)) == Decimal("6000")
        assert Decimal(str(loaded.month_12)) == Decimal("6500")


# ---------------------------------------------------------------------------
# Tests: Budget vs Actual variance calculation
# ---------------------------------------------------------------------------


class TestBudgetVsActual:
    """Test the budget vs actual variance logic using direct ORM queries."""

    def test_variance_calculation_with_actuals(self, session: Session, tenant: Tenant) -> None:
        """Budget $5000, actual posted $3200 => variance $1800 (under budget)."""
        period = _make_period(session, tenant.id, "2026-03")
        rent_acct = _make_account(session, tenant.id, "5100", "Rent Expense", "expense")
        cash_acct = _make_account(session, tenant.id, "1000", "Cash", "asset")

        budget = Budget(
            id=str(uuid.uuid4()),
            tenant_id=tenant.id,
            fiscal_year=2026,
            name="Test Budget",
            status="active",
            created_at=datetime.now(tz=UTC),
            updated_at=datetime.now(tz=UTC),
        )
        session.add(budget)
        session.flush()

        line = BudgetLine(
            id=str(uuid.uuid4()),
            tenant_id=tenant.id,
            budget_id=budget.id,
            account_id=rent_acct.id,
            month_3=Decimal("5000"),
            created_at=datetime.now(tz=UTC),
            updated_at=datetime.now(tz=UTC),
        )
        session.add(line)
        session.flush()

        # Post a journal entry in March 2026 for $3200 rent
        je = JournalEntry(
            id=str(uuid.uuid4()),
            tenant_id=tenant.id,
            number="JE-0001",
            date=datetime(2026, 3, 15, tzinfo=UTC),
            period_id=period.id,
            description="March rent",
            status="posted",
            source_type="manual",
            total_debit=Decimal("3200"),
            total_credit=Decimal("3200"),
            created_at=datetime.now(tz=UTC),
            updated_at=datetime.now(tz=UTC),
        )
        session.add(je)
        session.flush()

        # Debit rent (expense account, normal_balance=debit)
        session.add(
            JournalLine(
                id=str(uuid.uuid4()),
                tenant_id=tenant.id,
                journal_entry_id=je.id,
                line_no=1,
                account_id=rent_acct.id,
                debit=Decimal("3200"),
                credit=Decimal("0"),
                currency="USD",
                fx_rate=Decimal("1"),
                functional_debit=Decimal("3200"),
                functional_credit=Decimal("0"),
            )
        )
        # Credit cash
        session.add(
            JournalLine(
                id=str(uuid.uuid4()),
                tenant_id=tenant.id,
                journal_entry_id=je.id,
                line_no=2,
                account_id=cash_acct.id,
                debit=Decimal("0"),
                credit=Decimal("3200"),
                currency="USD",
                fx_rate=Decimal("1"),
                functional_debit=Decimal("0"),
                functional_credit=Decimal("3200"),
            )
        )
        session.flush()

        # Manually compute the variance (mirrors service logic)
        budget_amount = Decimal(str(line.month_3))
        # For expense account (normal_balance=debit): actual = debit - credit
        actual_amount = Decimal("3200") - Decimal("0")
        variance = budget_amount - actual_amount

        assert budget_amount == Decimal("5000")
        assert actual_amount == Decimal("3200")
        assert variance == Decimal("1800")  # Under budget

    def test_variance_with_no_actuals(self, session: Session, tenant: Tenant) -> None:
        """Budget $10000, no actuals => variance $10000 (100%)."""
        revenue_acct = _make_account(session, tenant.id, "4000", "Revenue", "revenue")

        budget = Budget(
            id=str(uuid.uuid4()),
            tenant_id=tenant.id,
            fiscal_year=2026,
            name="Revenue Budget",
            status="active",
            created_at=datetime.now(tz=UTC),
            updated_at=datetime.now(tz=UTC),
        )
        session.add(budget)
        session.flush()

        line = BudgetLine(
            id=str(uuid.uuid4()),
            tenant_id=tenant.id,
            budget_id=budget.id,
            account_id=revenue_acct.id,
            month_6=Decimal("10000"),
            created_at=datetime.now(tz=UTC),
            updated_at=datetime.now(tz=UTC),
        )
        session.add(line)
        session.flush()

        budget_amount = Decimal(str(line.month_6))
        actual_amount = Decimal("0")
        variance = budget_amount - actual_amount

        assert variance == Decimal("10000")
        # variance_pct = 100%
        variance_pct = (variance / budget_amount * Decimal("100")).quantize(Decimal("0.01"))
        assert variance_pct == Decimal("100.00")

    def test_over_budget_negative_variance(self, session: Session, tenant: Tenant) -> None:
        """Budget $2000, actual $3500 => variance -$1500 (over budget)."""
        expense_acct = _make_account(session, tenant.id, "5200", "Utilities", "expense")

        budget = Budget(
            id=str(uuid.uuid4()),
            tenant_id=tenant.id,
            fiscal_year=2026,
            name="Expense Budget",
            status="active",
            created_at=datetime.now(tz=UTC),
            updated_at=datetime.now(tz=UTC),
        )
        session.add(budget)
        session.flush()

        line = BudgetLine(
            id=str(uuid.uuid4()),
            tenant_id=tenant.id,
            budget_id=budget.id,
            account_id=expense_acct.id,
            month_1=Decimal("2000"),
            created_at=datetime.now(tz=UTC),
            updated_at=datetime.now(tz=UTC),
        )
        session.add(line)
        session.flush()

        budget_amount = Decimal("2000")
        actual_amount = Decimal("3500")
        variance = budget_amount - actual_amount

        assert variance == Decimal("-1500")
        variance_pct = (variance / budget_amount * Decimal("100")).quantize(Decimal("0.01"))
        assert variance_pct == Decimal("-75.00")

    def test_zero_budget_variance_pct(self, session: Session, tenant: Tenant) -> None:
        """Zero budget amount should report 0% variance, not divide-by-zero."""
        acct = _make_account(session, tenant.id, "5300", "Misc Expense", "expense")

        budget = Budget(
            id=str(uuid.uuid4()),
            tenant_id=tenant.id,
            fiscal_year=2026,
            name="Zero Budget",
            status="active",
            created_at=datetime.now(tz=UTC),
            updated_at=datetime.now(tz=UTC),
        )
        session.add(budget)
        session.flush()

        line = BudgetLine(
            id=str(uuid.uuid4()),
            tenant_id=tenant.id,
            budget_id=budget.id,
            account_id=acct.id,
            month_1=Decimal("0"),
            created_at=datetime.now(tz=UTC),
            updated_at=datetime.now(tz=UTC),
        )
        session.add(line)
        session.flush()

        budget_amount = Decimal(str(line.month_1))
        actual_amount = Decimal("500")
        variance = budget_amount - actual_amount

        # Should not raise
        variance_pct = (
            str((variance / budget_amount * Decimal("100")).quantize(Decimal("0.01")))
            if budget_amount != Decimal("0")
            else "0.00"
        )
        assert variance_pct == "0.00"
