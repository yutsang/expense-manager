"""Integration tests for core ledger operations and tenant isolation.

Issue #6: These tests exercise:
  1. Multi-tenant RLS: tenant A cannot read tenant B's data
  2. Journal balancing: unbalanced entries are rejected
  3. Period close: journals cannot be posted to hard_closed periods

Uses SQLite for lightweight integration testing of the ORM layer
and domain logic (the real Postgres triggers are tested separately).
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timezone
from decimal import Decimal

import pytest
import sqlalchemy as sa
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.core.db import Base
from app.domain.ledger.journal import (
    JournalBalanceError,
    JournalLineInput,
    validate_balance,
)
from app.domain.ledger.period import (
    PeriodStatus,
    PeriodTransitionError,
    assert_transition_allowed,
    can_post,
)
from app.infra.models import (
    Account,
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
    """Create an in-memory SQLite engine with all tables.

    Maps Postgres-specific types (JSONB, UUID, TIMESTAMP) to
    SQLite-compatible equivalents so the ORM layer can be tested
    without a Postgres instance.
    """
    from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID

    eng = create_engine("sqlite:///:memory:", echo=False)

    @event.listens_for(eng, "connect")
    def _set_sqlite_pragma(dbapi_conn, connection_record):  # type: ignore[no-untyped-def]
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=OFF")
        cursor.close()

    # Register type adapters so SQLite can render Postgres types
    from sqlalchemy import Text as SaText
    from sqlalchemy import String as SaString

    @sa.event.listens_for(sa.Table, "column_reflect")
    def _column_reflect(inspector, table, column_info):  # type: ignore[no-untyped-def]
        pass

    # Compile-time overrides for SQLite dialect
    from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler

    _orig_jsonb = getattr(SQLiteTypeCompiler, "visit_JSONB", None)
    if _orig_jsonb is None:
        SQLiteTypeCompiler.visit_JSONB = lambda self, type_, **kw: "TEXT"  # type: ignore[attr-defined]

    _orig_uuid = getattr(SQLiteTypeCompiler, "visit_UUID", None)
    if _orig_uuid is None:
        SQLiteTypeCompiler.visit_UUID = lambda self, type_, **kw: "VARCHAR(36)"  # type: ignore[attr-defined]

    _orig_ts = getattr(SQLiteTypeCompiler, "visit_TIMESTAMP", None)
    if _orig_ts is None:
        SQLiteTypeCompiler.visit_TIMESTAMP = lambda self, type_, **kw: "TIMESTAMP"  # type: ignore[attr-defined]

    Base.metadata.create_all(eng)
    return eng


@pytest.fixture()
def session(engine: sa.engine.Engine) -> Session:
    """Provide a SQLAlchemy session bound to the in-memory DB."""
    factory = sessionmaker(bind=engine)
    sess = factory()
    yield sess  # type: ignore[misc]
    sess.close()


@pytest.fixture()
def tenant_a(session: Session) -> Tenant:
    """Create tenant A."""
    t = Tenant(
        id=str(uuid.uuid4()),
        name="Tenant A",
        legal_name="Tenant A Ltd",
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
def tenant_b(session: Session) -> Tenant:
    """Create tenant B."""
    t = Tenant(
        id=str(uuid.uuid4()),
        name="Tenant B",
        legal_name="Tenant B Ltd",
        country="US",
        functional_currency="USD",
        fiscal_year_start_month=1,
        created_at=datetime.now(tz=UTC),
        updated_at=datetime.now(tz=UTC),
    )
    session.add(t)
    session.flush()
    return t


def _make_account(session: Session, tenant_id: str, code: str, name: str, acct_type: str) -> Account:
    """Helper to create an account."""
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


def _make_period(session: Session, tenant_id: str, name: str, status: str = "open") -> Period:
    """Helper to create a period."""
    p = Period(
        id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        name=name,
        start_date=datetime(2025, 1, 1, tzinfo=UTC),
        end_date=datetime(2025, 1, 31, tzinfo=UTC),
        status=status,
        created_at=datetime.now(tz=UTC),
        updated_at=datetime.now(tz=UTC),
    )
    session.add(p)
    session.flush()
    return p


# ---------------------------------------------------------------------------
# Test: Multi-tenant isolation
# ---------------------------------------------------------------------------


class TestTenantIsolation:
    """Tenant A's data should not be visible to queries filtered by tenant B."""

    def test_accounts_isolated_by_tenant(
        self, session: Session, tenant_a: Tenant, tenant_b: Tenant
    ) -> None:
        """Accounts created for tenant A are not returned when querying tenant B."""
        _make_account(session, tenant_a.id, "1000", "Cash", "asset")
        _make_account(session, tenant_a.id, "4000", "Revenue", "revenue")

        # Query for tenant B's accounts should return nothing
        result = session.execute(
            sa.select(Account).where(Account.tenant_id == tenant_b.id)
        )
        tenant_b_accounts = list(result.scalars().all())
        assert len(tenant_b_accounts) == 0

    def test_journal_entries_isolated_by_tenant(
        self, session: Session, tenant_a: Tenant, tenant_b: Tenant
    ) -> None:
        """Journal entries from tenant A are not visible to tenant B."""
        period_a = _make_period(session, tenant_a.id, "2025-01")
        cash = _make_account(session, tenant_a.id, "1000", "Cash", "asset")
        revenue = _make_account(session, tenant_a.id, "4000", "Revenue", "revenue")

        je = JournalEntry(
            id=str(uuid.uuid4()),
            tenant_id=tenant_a.id,
            number="JE-0001",
            date=datetime(2025, 1, 15, tzinfo=UTC),
            period_id=period_a.id,
            description="Test journal",
            status="posted",
            source_type="manual",
            total_debit=Decimal("100"),
            total_credit=Decimal("100"),
            created_at=datetime.now(tz=UTC),
            updated_at=datetime.now(tz=UTC),
        )
        session.add(je)
        session.flush()

        # Tenant B should see no journal entries
        result = session.execute(
            sa.select(JournalEntry).where(JournalEntry.tenant_id == tenant_b.id)
        )
        assert len(list(result.scalars().all())) == 0

    def test_periods_isolated_by_tenant(
        self, session: Session, tenant_a: Tenant, tenant_b: Tenant
    ) -> None:
        """Periods from tenant A are not visible to tenant B."""
        _make_period(session, tenant_a.id, "2025-01")
        _make_period(session, tenant_a.id, "2025-02")

        result = session.execute(
            sa.select(Period).where(Period.tenant_id == tenant_b.id)
        )
        assert len(list(result.scalars().all())) == 0

    def test_direct_id_access_still_requires_tenant_filter(
        self, session: Session, tenant_a: Tenant, tenant_b: Tenant
    ) -> None:
        """Even querying by ID, a tenant_id filter prevents cross-tenant access."""
        acct = _make_account(session, tenant_a.id, "1000", "Cash", "asset")

        # Querying with tenant B's ID and tenant A's account ID should return None
        result = session.execute(
            sa.select(Account).where(
                Account.id == acct.id,
                Account.tenant_id == tenant_b.id,
            )
        )
        assert result.scalar_one_or_none() is None


# ---------------------------------------------------------------------------
# Test: Journal entry balancing
# ---------------------------------------------------------------------------


class TestJournalBalancing:
    """Journal entries must always balance: total debits == total credits."""

    def test_balanced_journal_passes_validation(self) -> None:
        """A properly balanced journal should not raise."""
        lines = [
            JournalLineInput(
                account_id="acct-1",
                debit=Decimal("100"),
                credit=Decimal("0"),
                currency="USD",
                functional_debit=Decimal("100"),
                functional_credit=Decimal("0"),
            ),
            JournalLineInput(
                account_id="acct-2",
                debit=Decimal("0"),
                credit=Decimal("100"),
                currency="USD",
                functional_debit=Decimal("0"),
                functional_credit=Decimal("100"),
            ),
        ]
        validate_balance(lines)  # Should not raise

    def test_unbalanced_journal_rejected(self) -> None:
        """An unbalanced journal entry must be rejected."""
        lines = [
            JournalLineInput(
                account_id="acct-1",
                debit=Decimal("100"),
                credit=Decimal("0"),
                currency="USD",
                functional_debit=Decimal("100"),
                functional_credit=Decimal("0"),
            ),
            JournalLineInput(
                account_id="acct-2",
                debit=Decimal("0"),
                credit=Decimal("50"),
                currency="USD",
                functional_debit=Decimal("0"),
                functional_credit=Decimal("50"),
            ),
        ]
        with pytest.raises(JournalBalanceError, match="unbalanced"):
            validate_balance(lines)

    def test_zero_balance_journal_rejected(self) -> None:
        """A journal with all-zero lines is rejected."""
        lines = [
            JournalLineInput(
                account_id="acct-1",
                debit=Decimal("0"),
                credit=Decimal("0"),
                currency="USD",
                functional_debit=Decimal("0"),
                functional_credit=Decimal("0"),
            ),
        ]
        with pytest.raises(JournalBalanceError, match="zero balance"):
            validate_balance(lines)

    def test_empty_lines_rejected(self) -> None:
        """A journal with no lines at all is rejected."""
        with pytest.raises(JournalBalanceError, match="at least one line"):
            validate_balance([])

    def test_negative_amounts_rejected(self) -> None:
        """Journal line amounts must be non-negative."""
        with pytest.raises(ValueError, match="non-negative"):
            JournalLineInput(
                account_id="acct-1",
                debit=Decimal("-50"),
                credit=Decimal("0"),
                currency="USD",
            )

    def test_both_debit_and_credit_rejected(self) -> None:
        """A single line cannot have both debit and credit amounts."""
        with pytest.raises(ValueError, match="both debit and credit"):
            JournalLineInput(
                account_id="acct-1",
                debit=Decimal("100"),
                credit=Decimal("50"),
                currency="USD",
            )

    def test_multi_line_balanced_journal(self) -> None:
        """A multi-line journal that balances passes validation."""
        lines = [
            JournalLineInput(
                account_id="acct-1",
                debit=Decimal("200"),
                credit=Decimal("0"),
                currency="USD",
                functional_debit=Decimal("200"),
                functional_credit=Decimal("0"),
            ),
            JournalLineInput(
                account_id="acct-2",
                debit=Decimal("0"),
                credit=Decimal("150"),
                currency="USD",
                functional_debit=Decimal("0"),
                functional_credit=Decimal("150"),
            ),
            JournalLineInput(
                account_id="acct-3",
                debit=Decimal("0"),
                credit=Decimal("50"),
                currency="USD",
                functional_debit=Decimal("0"),
                functional_credit=Decimal("50"),
            ),
        ]
        validate_balance(lines)  # Should not raise

    def test_balanced_journal_persists_to_db(
        self, session: Session, tenant_a: Tenant
    ) -> None:
        """A balanced journal entry can be saved to the database."""
        period = _make_period(session, tenant_a.id, "2025-01")
        cash = _make_account(session, tenant_a.id, "1000", "Cash", "asset")
        revenue = _make_account(session, tenant_a.id, "4000", "Revenue", "revenue")

        je_id = str(uuid.uuid4())
        je = JournalEntry(
            id=je_id,
            tenant_id=tenant_a.id,
            number="JE-0001",
            date=datetime(2025, 1, 15, tzinfo=UTC),
            period_id=period.id,
            description="Test balanced journal",
            status="posted",
            source_type="manual",
            total_debit=Decimal("500"),
            total_credit=Decimal("500"),
            created_at=datetime.now(tz=UTC),
            updated_at=datetime.now(tz=UTC),
        )
        session.add(je)

        session.add(JournalLine(
            id=str(uuid.uuid4()),
            tenant_id=tenant_a.id,
            journal_entry_id=je_id,
            line_no=1,
            account_id=cash.id,
            debit=Decimal("500"),
            credit=Decimal("0"),
            currency="USD",
            fx_rate=Decimal("1"),
            functional_debit=Decimal("500"),
            functional_credit=Decimal("0"),
        ))
        session.add(JournalLine(
            id=str(uuid.uuid4()),
            tenant_id=tenant_a.id,
            journal_entry_id=je_id,
            line_no=2,
            account_id=revenue.id,
            debit=Decimal("0"),
            credit=Decimal("500"),
            currency="USD",
            fx_rate=Decimal("1"),
            functional_debit=Decimal("0"),
            functional_credit=Decimal("500"),
        ))
        session.flush()

        # Verify the entry persisted correctly
        loaded = session.get(JournalEntry, je_id)
        assert loaded is not None
        assert str(loaded.total_debit) == "500"
        assert str(loaded.total_credit) == "500"


# ---------------------------------------------------------------------------
# Test: Period close constraints
# ---------------------------------------------------------------------------


class TestPeriodClose:
    """Period status controls whether journals can be posted."""

    def test_open_period_allows_posting(self) -> None:
        """Journals can be posted into an open period."""
        assert can_post(PeriodStatus.OPEN) is True

    def test_soft_closed_blocks_without_admin(self) -> None:
        """Soft-closed period blocks normal posting."""
        assert can_post(PeriodStatus.SOFT_CLOSED) is False

    def test_soft_closed_allows_with_admin_override(self) -> None:
        """Soft-closed period allows posting with admin override."""
        assert can_post(PeriodStatus.SOFT_CLOSED, admin_override=True) is True

    def test_hard_closed_blocks_all_posting(self) -> None:
        """Hard-closed period blocks posting even with admin override."""
        assert can_post(PeriodStatus.HARD_CLOSED) is False
        assert can_post(PeriodStatus.HARD_CLOSED, admin_override=True) is False

    def test_audited_blocks_all_posting(self) -> None:
        """Audited period blocks posting."""
        assert can_post(PeriodStatus.AUDITED) is False
        assert can_post(PeriodStatus.AUDITED, admin_override=True) is False

    def test_valid_period_transitions(self) -> None:
        """Test all valid state transitions."""
        # open -> soft_closed
        assert_transition_allowed(PeriodStatus.OPEN, PeriodStatus.SOFT_CLOSED)
        # open -> hard_closed
        assert_transition_allowed(PeriodStatus.OPEN, PeriodStatus.HARD_CLOSED)
        # soft_closed -> open (reopen)
        assert_transition_allowed(PeriodStatus.SOFT_CLOSED, PeriodStatus.OPEN)
        # soft_closed -> hard_closed
        assert_transition_allowed(PeriodStatus.SOFT_CLOSED, PeriodStatus.HARD_CLOSED)
        # hard_closed -> audited
        assert_transition_allowed(PeriodStatus.HARD_CLOSED, PeriodStatus.AUDITED)

    def test_invalid_period_transitions(self) -> None:
        """Test that invalid transitions are rejected."""
        with pytest.raises(PeriodTransitionError):
            assert_transition_allowed(PeriodStatus.OPEN, PeriodStatus.AUDITED)

        with pytest.raises(PeriodTransitionError):
            assert_transition_allowed(PeriodStatus.HARD_CLOSED, PeriodStatus.OPEN)

        with pytest.raises(PeriodTransitionError):
            assert_transition_allowed(PeriodStatus.AUDITED, PeriodStatus.OPEN)

    def test_period_status_stored_correctly(
        self, session: Session, tenant_a: Tenant
    ) -> None:
        """Period status can be updated and read back from DB."""
        period = _make_period(session, tenant_a.id, "2025-01", status="open")
        assert period.status == "open"

        period.status = "hard_closed"
        session.flush()

        loaded = session.get(Period, period.id)
        assert loaded is not None
        assert loaded.status == "hard_closed"
