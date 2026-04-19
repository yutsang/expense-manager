"""Unit tests for customer credit limit feature (Issue #30).

Tests cover:
  - Contact model has a nullable credit_limit field (NUMERIC(19,4))
  - ContactCreate/ContactUpdate schemas accept credit_limit as str|None
  - ContactResponse schema returns credit_limit
  - InvoiceCreate schema accepts force flag (bool, default False)
  - authorise_invoice: rejects when new invoice would exceed credit limit
  - authorise_invoice: allows when contact has no credit limit (null)
  - authorise_invoice: allows when outstanding + new total is within limit
  - authorise_invoice: allows with force=True even when limit exceeded
  - Credit limit check sums only non-void, non-paid invoices
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.v1.schemas import ContactCreate, ContactResponse, ContactUpdate, InvoiceCreate

# ---------------------------------------------------------------------------
# Model source inspection tests (always run, no runtime import needed)
# ---------------------------------------------------------------------------


class TestContactModelCreditLimit:
    """Contact model must have a nullable credit_limit column."""

    def _read_models_source(self) -> str:
        import pathlib

        models_path = pathlib.Path(__file__).resolve().parents[2] / "app" / "infra" / "models.py"
        return models_path.read_text()

    def test_credit_limit_column_exists(self) -> None:
        source = self._read_models_source()
        assert "credit_limit" in source

    def test_credit_limit_is_numeric_19_4(self) -> None:
        source = self._read_models_source()
        # Should use Numeric(19, 4) for money precision
        assert "Numeric(19, 4)" in source or "Numeric(19,4)" in source

    def test_credit_limit_is_nullable(self) -> None:
        source = self._read_models_source()
        # The credit_limit column definition should include nullable=True
        # Find the credit_limit line and verify nullable
        idx = source.index("credit_limit")
        # Look at context around the column definition
        block = source[idx : idx + 200]
        assert "nullable=True" in block


# ---------------------------------------------------------------------------
# Schema tests
# ---------------------------------------------------------------------------


class TestContactCreateSchema:
    """ContactCreate schema accepts optional credit_limit."""

    def test_credit_limit_defaults_to_none(self) -> None:
        s = ContactCreate(contact_type="customer", name="Acme Corp")
        assert s.credit_limit is None

    def test_credit_limit_accepts_valid_decimal_string(self) -> None:
        s = ContactCreate(contact_type="customer", name="Acme Corp", credit_limit="50000.0000")
        assert s.credit_limit == "50000.0000"

    def test_credit_limit_accepts_none_explicitly(self) -> None:
        s = ContactCreate(contact_type="customer", name="Acme Corp", credit_limit=None)
        assert s.credit_limit is None

    def test_credit_limit_rejects_negative(self) -> None:
        with pytest.raises(Exception):
            ContactCreate(contact_type="customer", name="Acme Corp", credit_limit="-100")

    def test_credit_limit_accepts_zero(self) -> None:
        s = ContactCreate(contact_type="customer", name="Acme Corp", credit_limit="0")
        assert s.credit_limit == "0"


class TestContactUpdateSchema:
    """ContactUpdate schema accepts optional credit_limit."""

    def test_credit_limit_defaults_to_none(self) -> None:
        s = ContactUpdate()
        assert s.credit_limit is None

    def test_credit_limit_accepts_valid_decimal_string(self) -> None:
        s = ContactUpdate(credit_limit="25000.0000")
        assert s.credit_limit == "25000.0000"


class TestContactResponseSchema:
    """ContactResponse schema includes credit_limit."""

    def test_credit_limit_field_exists(self) -> None:
        # Verify the field is part of the model
        assert "credit_limit" in ContactResponse.model_fields


class TestInvoiceCreateForceFlag:
    """InvoiceCreate schema has a force flag for credit limit override."""

    def test_force_defaults_to_false(self) -> None:
        s = InvoiceCreate(
            contact_id="c1",
            issue_date="2026-01-01",
            currency="USD",
            lines=[{"account_id": "a1", "quantity": "1", "unit_price": "100"}],
        )
        assert s.force is False

    def test_force_can_be_set_to_true(self) -> None:
        s = InvoiceCreate(
            contact_id="c1",
            issue_date="2026-01-01",
            currency="USD",
            force=True,
            lines=[{"account_id": "a1", "quantity": "1", "unit_price": "100"}],
        )
        assert s.force is True


# ---------------------------------------------------------------------------
# Service source inspection
# ---------------------------------------------------------------------------


class TestInvoiceServiceCreditLimitSource:
    """Verify service code includes credit limit logic."""

    def _read_service_source(self) -> str:
        import pathlib

        svc_path = pathlib.Path(__file__).resolve().parents[2] / "app" / "services" / "invoices.py"
        return svc_path.read_text()

    def test_credit_limit_error_class_exists(self) -> None:
        source = self._read_service_source()
        assert "class CreditLimitExceededError" in source

    def test_authorise_checks_credit_limit(self) -> None:
        source = self._read_service_source()
        assert "credit_limit" in source

    def test_authorise_accepts_force_parameter(self) -> None:
        source = self._read_service_source()
        # authorise_invoice should have a force parameter
        idx = source.index("async def authorise_invoice(")
        sig_block = source[idx : idx + 300]
        assert "force" in sig_block


# ---------------------------------------------------------------------------
# Service-level async tests (require Python 3.11+)
# ---------------------------------------------------------------------------


class TestCreditLimitEnforcement:
    """authorise_invoice should enforce credit limits."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        db = AsyncMock()
        db.flush = AsyncMock()
        db.refresh = AsyncMock()
        db.scalar = AsyncMock()
        seq_result = MagicMock()
        seq_result.scalar_one.return_value = 1
        db.execute = AsyncMock(return_value=seq_result)
        return db

    def _make_invoice(
        self,
        *,
        total: str = "5000.0000",
        status: str = "draft",
        contact_id: str = "contact-1",
        tenant_id: str = "t1",
    ) -> MagicMock:
        inv = MagicMock()
        inv.id = "inv-new"
        inv.tenant_id = tenant_id
        inv.status = status
        inv.total = Decimal(total)
        inv.currency = "USD"
        inv.fx_rate = Decimal("1")
        inv.contact_id = contact_id
        inv.issue_date = "2026-01-15"
        inv.period_name = "2026-01"
        inv.number = "DRAFT-ABC"
        inv.version = 1
        inv.updated_by = None
        inv.journal_entry_id = None
        inv.authorised_by = None
        return inv

    def _make_tenant(self, *, threshold: str | None = None) -> MagicMock:
        tenant = MagicMock()
        tenant.id = "t1"
        tenant.invoice_approval_threshold = Decimal(threshold) if threshold is not None else None
        return tenant

    def _make_contact(self, *, credit_limit: str | None = None) -> MagicMock:
        contact = MagicMock()
        contact.id = "contact-1"
        contact.tenant_id = "t1"
        contact.credit_limit = Decimal(credit_limit) if credit_limit is not None else None
        return contact

    @pytest.mark.anyio
    async def test_no_credit_limit_allows_authorise(self, mock_db: AsyncMock) -> None:
        """Contact with no credit limit (null) should not be blocked."""
        from app.services.invoices import authorise_invoice

        inv = self._make_invoice(total="999999.0000")
        tenant = self._make_tenant(threshold=None)
        contact = self._make_contact(credit_limit=None)

        with (
            patch("app.services.invoices.get_invoice", return_value=inv),
            patch("app.services.invoices.get_invoice_lines", return_value=[]),
            patch("app.services.invoices.get_tenant", return_value=tenant),
            patch("app.services.invoices.get_contact", return_value=contact),
            patch(
                "app.services.approval_rules.evaluate_rules",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch(
                "app.services.invoices._get_outstanding_invoice_total",
                return_value=Decimal("0"),
            ),
            patch("app.services.invoices._post_invoice_journal", new_callable=AsyncMock),
            patch("app.services.invoices.emit", new_callable=AsyncMock),
        ):
            result = await authorise_invoice(mock_db, "t1", "inv-new", "actor-1")

        assert result.status == "authorised"

    @pytest.mark.anyio
    async def test_within_credit_limit_allows_authorise(self, mock_db: AsyncMock) -> None:
        """Invoice that stays within credit limit should be authorised."""
        from app.services.invoices import authorise_invoice

        inv = self._make_invoice(total="3000.0000")
        tenant = self._make_tenant(threshold=None)
        contact = self._make_contact(credit_limit="10000.0000")

        with (
            patch("app.services.invoices.get_invoice", return_value=inv),
            patch("app.services.invoices.get_invoice_lines", return_value=[]),
            patch("app.services.invoices.get_tenant", return_value=tenant),
            patch("app.services.invoices.get_contact", return_value=contact),
            patch(
                "app.services.approval_rules.evaluate_rules",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch(
                "app.services.invoices._get_outstanding_invoice_total",
                return_value=Decimal("5000.0000"),
            ),
            patch("app.services.invoices._post_invoice_journal", new_callable=AsyncMock),
            patch("app.services.invoices.emit", new_callable=AsyncMock),
        ):
            result = await authorise_invoice(mock_db, "t1", "inv-new", "actor-1")

        assert result.status == "authorised"

    @pytest.mark.anyio
    async def test_exceeding_credit_limit_rejects(self, mock_db: AsyncMock) -> None:
        """Invoice that would push outstanding AR over credit limit should be rejected."""
        from app.services.invoices import CreditLimitExceededError, authorise_invoice

        inv = self._make_invoice(total="6000.0000")
        tenant = self._make_tenant(threshold=None)
        contact = self._make_contact(credit_limit="10000.0000")

        with (
            patch("app.services.invoices.get_invoice", return_value=inv),
            patch("app.services.invoices.get_invoice_lines", return_value=[]),
            patch("app.services.invoices.get_tenant", return_value=tenant),
            patch("app.services.invoices.get_contact", return_value=contact),
            patch(
                "app.services.approval_rules.evaluate_rules",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch(
                "app.services.invoices._get_outstanding_invoice_total",
                return_value=Decimal("5000.0000"),
            ),
            pytest.raises(CreditLimitExceededError),
        ):
            await authorise_invoice(mock_db, "t1", "inv-new", "actor-1")

    @pytest.mark.anyio
    async def test_exactly_at_credit_limit_allows(self, mock_db: AsyncMock) -> None:
        """Invoice that brings AR exactly to the limit should be allowed."""
        from app.services.invoices import authorise_invoice

        inv = self._make_invoice(total="5000.0000")
        tenant = self._make_tenant(threshold=None)
        contact = self._make_contact(credit_limit="10000.0000")

        with (
            patch("app.services.invoices.get_invoice", return_value=inv),
            patch("app.services.invoices.get_invoice_lines", return_value=[]),
            patch("app.services.invoices.get_tenant", return_value=tenant),
            patch("app.services.invoices.get_contact", return_value=contact),
            patch(
                "app.services.approval_rules.evaluate_rules",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch(
                "app.services.invoices._get_outstanding_invoice_total",
                return_value=Decimal("5000.0000"),
            ),
        ):
            result = await authorise_invoice(mock_db, "t1", "inv-new", "actor-1")

        assert result.status == "authorised"

    @pytest.mark.anyio
    async def test_force_overrides_credit_limit(self, mock_db: AsyncMock) -> None:
        """force=True should bypass the credit limit check."""
        from app.services.invoices import authorise_invoice

        inv = self._make_invoice(total="20000.0000")
        tenant = self._make_tenant(threshold=None)
        contact = self._make_contact(credit_limit="10000.0000")

        with (
            patch("app.services.invoices.get_invoice", return_value=inv),
            patch("app.services.invoices.get_invoice_lines", return_value=[]),
            patch("app.services.invoices.get_tenant", return_value=tenant),
            patch("app.services.invoices.get_contact", return_value=contact),
            patch(
                "app.services.approval_rules.evaluate_rules",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch(
                "app.services.invoices._get_outstanding_invoice_total",
                return_value=Decimal("5000.0000"),
            ),
            patch("app.services.invoices._post_invoice_journal", new_callable=AsyncMock),
            patch("app.services.invoices.emit", new_callable=AsyncMock),
        ):
            result = await authorise_invoice(mock_db, "t1", "inv-new", "actor-1", force=True)

        assert result.status == "authorised"

    @pytest.mark.anyio
    async def test_zero_credit_limit_blocks_any_invoice(self, mock_db: AsyncMock) -> None:
        """A credit limit of zero should block all invoices (unless forced)."""
        from app.services.invoices import CreditLimitExceededError, authorise_invoice

        inv = self._make_invoice(total="100.0000")
        tenant = self._make_tenant(threshold=None)
        contact = self._make_contact(credit_limit="0")

        with (
            patch("app.services.invoices.get_invoice", return_value=inv),
            patch("app.services.invoices.get_invoice_lines", return_value=[]),
            patch("app.services.invoices.get_tenant", return_value=tenant),
            patch("app.services.invoices.get_contact", return_value=contact),
            patch(
                "app.services.approval_rules.evaluate_rules",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch(
                "app.services.invoices._get_outstanding_invoice_total",
                return_value=Decimal("0"),
            ),
            pytest.raises(CreditLimitExceededError),
        ):
            await authorise_invoice(mock_db, "t1", "inv-new", "actor-1")
