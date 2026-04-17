"""Unit tests for DNFBP classification and risk rating (Issue #35).

AMLO Cap 615 compliance: contacts need risk_rating, risk_rating_rationale,
risk_rated_by, risk_rated_at, edd_required, edd_approved_by, edd_approved_at
fields. Contacts with risk_rating='unacceptable' block invoice creation.

Tests cover:
  - Contact model has all required risk rating columns
  - RiskRatingUpdate schema validates allowed rating values
  - ContactResponse schema returns risk rating fields
  - KycDashboardAlerts schema includes unrated_contacts count
  - set_risk_rating service: sets rating, records actor and timestamp
  - set_risk_rating service: 'high' sets edd_required=True automatically
  - set_risk_rating service: 'unacceptable' sets edd_required=True
  - set_risk_rating service: 'low'/'medium' leaves edd_required=False
  - authorise_invoice: rejects when contact has risk_rating='unacceptable'
  - authorise_invoice: allows when contact has risk_rating='high' with EDD approved
  - approve_edd service: sets edd_approved_by and edd_approved_at
"""

from __future__ import annotations

import sys
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.v1.schemas import ContactResponse

_NEEDS_311 = sys.version_info < (3, 11)
_skip_311 = pytest.mark.skipif(_NEEDS_311, reason="datetime.UTC requires Python >=3.11")


# ---------------------------------------------------------------------------
# Model source inspection tests (always run, no runtime import needed)
# ---------------------------------------------------------------------------


class TestContactModelRiskRating:
    """Contact model must have risk rating columns for AMLO Cap 615."""

    def _read_models_source(self) -> str:
        import pathlib

        models_path = pathlib.Path(__file__).resolve().parents[2] / "app" / "infra" / "models.py"
        return models_path.read_text()

    def test_risk_rating_column_exists(self) -> None:
        source = self._read_models_source()
        assert "risk_rating" in source

    def test_risk_rating_rationale_column_exists(self) -> None:
        source = self._read_models_source()
        assert "risk_rating_rationale" in source

    def test_risk_rated_by_column_exists(self) -> None:
        source = self._read_models_source()
        assert "risk_rated_by" in source

    def test_risk_rated_at_column_exists(self) -> None:
        source = self._read_models_source()
        assert "risk_rated_at" in source

    def test_edd_required_column_exists(self) -> None:
        source = self._read_models_source()
        assert "edd_required" in source

    def test_edd_approved_by_column_exists(self) -> None:
        source = self._read_models_source()
        assert "edd_approved_by" in source

    def test_edd_approved_at_column_exists(self) -> None:
        source = self._read_models_source()
        assert "edd_approved_at" in source

    def test_risk_rating_is_nullable(self) -> None:
        """risk_rating should be nullable (unrated contacts have NULL)."""
        source = self._read_models_source()
        idx = source.index("risk_rating")
        # Find the mapped_column call for risk_rating (not risk_rating_rationale)
        block = source[idx : idx + 200]
        assert "nullable=True" in block

    def test_edd_required_defaults_to_false(self) -> None:
        source = self._read_models_source()
        idx = source.index("edd_required")
        block = source[idx : idx + 200]
        assert "default=False" in block

    def test_risk_rating_check_constraint_exists(self) -> None:
        """DB check constraint for valid risk_rating values."""
        source = self._read_models_source()
        assert (
            "low" in source and "medium" in source and "high" in source and "unacceptable" in source
        )


# ---------------------------------------------------------------------------
# Schema tests
# ---------------------------------------------------------------------------


class TestRiskRatingUpdateSchema:
    """RiskRatingUpdate schema validates risk rating values."""

    def test_valid_risk_ratings(self) -> None:
        from app.api.v1.schemas import RiskRatingUpdate

        for rating in ("low", "medium", "high", "unacceptable"):
            s = RiskRatingUpdate(risk_rating=rating, risk_rating_rationale="test reason")
            assert s.risk_rating == rating

    def test_rationale_is_required(self) -> None:
        from app.api.v1.schemas import RiskRatingUpdate

        with pytest.raises(Exception):
            RiskRatingUpdate(risk_rating="low")

    def test_invalid_risk_rating_rejected(self) -> None:
        from app.api.v1.schemas import RiskRatingUpdate

        with pytest.raises(Exception):
            RiskRatingUpdate(risk_rating="extreme", risk_rating_rationale="test")


class TestContactResponseRiskFields:
    """ContactResponse schema includes risk rating fields."""

    def test_risk_rating_field_exists(self) -> None:
        assert "risk_rating" in ContactResponse.model_fields

    def test_edd_required_field_exists(self) -> None:
        assert "edd_required" in ContactResponse.model_fields

    def test_risk_rated_at_field_exists(self) -> None:
        assert "risk_rated_at" in ContactResponse.model_fields

    def test_risk_rated_by_field_exists(self) -> None:
        assert "risk_rated_by" in ContactResponse.model_fields

    def test_edd_approved_by_field_exists(self) -> None:
        assert "edd_approved_by" in ContactResponse.model_fields

    def test_edd_approved_at_field_exists(self) -> None:
        assert "edd_approved_at" in ContactResponse.model_fields

    def test_risk_rating_rationale_field_exists(self) -> None:
        assert "risk_rating_rationale" in ContactResponse.model_fields


class TestKycDashboardUnrated:
    """KycDashboardAlerts schema includes unrated_contacts count."""

    def test_unrated_contacts_field_exists(self) -> None:
        from app.api.v1.schemas import KycDashboardAlerts

        assert "unrated_contacts" in KycDashboardAlerts.model_fields


# ---------------------------------------------------------------------------
# Service source inspection
# ---------------------------------------------------------------------------


class TestContactServiceRiskRating:
    """Contact service includes set_risk_rating and approve_edd functions."""

    def _read_service_source(self) -> str:
        import pathlib

        svc_path = pathlib.Path(__file__).resolve().parents[2] / "app" / "services" / "contacts.py"
        return svc_path.read_text()

    def test_set_risk_rating_function_exists(self) -> None:
        source = self._read_service_source()
        assert "async def set_risk_rating(" in source

    def test_approve_edd_function_exists(self) -> None:
        source = self._read_service_source()
        assert "async def approve_edd(" in source

    def test_compliance_restriction_error_exists(self) -> None:
        source = self._read_service_source()
        assert "class ComplianceRestrictionError" in source


class TestInvoiceServiceRiskRatingGuard:
    """Invoice authorise checks contact risk_rating."""

    def _read_service_source(self) -> str:
        import pathlib

        svc_path = pathlib.Path(__file__).resolve().parents[2] / "app" / "services" / "invoices.py"
        return svc_path.read_text()

    def test_authorise_checks_risk_rating(self) -> None:
        source = self._read_service_source()
        assert "risk_rating" in source

    def test_unacceptable_rating_error(self) -> None:
        source = self._read_service_source()
        assert "unacceptable" in source


# ---------------------------------------------------------------------------
# Service-level async tests (require Python 3.11+)
# ---------------------------------------------------------------------------


@_skip_311
class TestSetRiskRating:
    """set_risk_rating service function tests."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        db = AsyncMock()
        db.flush = AsyncMock()
        db.refresh = AsyncMock()
        db.scalar = AsyncMock()
        return db

    def _make_contact(
        self,
        *,
        risk_rating: str | None = None,
        edd_required: bool = False,
    ) -> MagicMock:
        contact = MagicMock()
        contact.id = "contact-1"
        contact.tenant_id = "t1"
        contact.risk_rating = risk_rating
        contact.risk_rating_rationale = None
        contact.risk_rated_by = None
        contact.risk_rated_at = None
        contact.edd_required = edd_required
        contact.edd_approved_by = None
        contact.edd_approved_at = None
        contact.version = 1
        contact.updated_by = None
        return contact

    @pytest.mark.anyio
    async def test_set_low_rating(self, mock_db: AsyncMock) -> None:
        from app.services.contacts import set_risk_rating

        contact = self._make_contact()
        with patch("app.services.contacts.get_contact", return_value=contact):
            result = await set_risk_rating(
                mock_db,
                "t1",
                "contact-1",
                "actor-1",
                risk_rating="low",
                risk_rating_rationale="Standard customer, known entity",
            )
        assert result.risk_rating == "low"
        assert result.risk_rating_rationale == "Standard customer, known entity"
        assert result.edd_required is False

    @pytest.mark.anyio
    async def test_set_high_rating_enables_edd(self, mock_db: AsyncMock) -> None:
        from app.services.contacts import set_risk_rating

        contact = self._make_contact()
        with patch("app.services.contacts.get_contact", return_value=contact):
            result = await set_risk_rating(
                mock_db,
                "t1",
                "contact-1",
                "actor-1",
                risk_rating="high",
                risk_rating_rationale="PEP-adjacent entity",
            )
        assert result.risk_rating == "high"
        assert result.edd_required is True

    @pytest.mark.anyio
    async def test_set_unacceptable_rating_enables_edd(self, mock_db: AsyncMock) -> None:
        from app.services.contacts import set_risk_rating

        contact = self._make_contact()
        with patch("app.services.contacts.get_contact", return_value=contact):
            result = await set_risk_rating(
                mock_db,
                "t1",
                "contact-1",
                "actor-1",
                risk_rating="unacceptable",
                risk_rating_rationale="FATF grey-listed jurisdiction",
            )
        assert result.risk_rating == "unacceptable"
        assert result.edd_required is True

    @pytest.mark.anyio
    async def test_set_medium_rating_no_edd(self, mock_db: AsyncMock) -> None:
        from app.services.contacts import set_risk_rating

        contact = self._make_contact()
        with patch("app.services.contacts.get_contact", return_value=contact):
            result = await set_risk_rating(
                mock_db,
                "t1",
                "contact-1",
                "actor-1",
                risk_rating="medium",
                risk_rating_rationale="Moderate risk assessment",
            )
        assert result.risk_rating == "medium"
        assert result.edd_required is False

    @pytest.mark.anyio
    async def test_risk_rating_records_actor_and_timestamp(self, mock_db: AsyncMock) -> None:
        from app.services.contacts import set_risk_rating

        contact = self._make_contact()
        with patch("app.services.contacts.get_contact", return_value=contact):
            result = await set_risk_rating(
                mock_db,
                "t1",
                "contact-1",
                "actor-1",
                risk_rating="low",
                risk_rating_rationale="Known entity",
            )
        assert result.risk_rated_by == "actor-1"
        assert result.risk_rated_at is not None


@_skip_311
class TestApproveEdd:
    """approve_edd service function tests."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        db = AsyncMock()
        db.flush = AsyncMock()
        db.refresh = AsyncMock()
        return db

    def _make_contact(
        self,
        *,
        edd_required: bool = True,
        risk_rating: str = "high",
    ) -> MagicMock:
        contact = MagicMock()
        contact.id = "contact-1"
        contact.tenant_id = "t1"
        contact.risk_rating = risk_rating
        contact.edd_required = edd_required
        contact.edd_approved_by = None
        contact.edd_approved_at = None
        contact.version = 1
        contact.updated_by = None
        return contact

    @pytest.mark.anyio
    async def test_approve_edd_sets_fields(self, mock_db: AsyncMock) -> None:
        from app.services.contacts import approve_edd

        contact = self._make_contact()
        with patch("app.services.contacts.get_contact", return_value=contact):
            result = await approve_edd(mock_db, "t1", "contact-1", "senior-user-1")
        assert result.edd_approved_by == "senior-user-1"
        assert result.edd_approved_at is not None

    @pytest.mark.anyio
    async def test_approve_edd_raises_if_not_required(self, mock_db: AsyncMock) -> None:
        from app.services.contacts import EddNotRequiredError, approve_edd

        contact = self._make_contact(edd_required=False)
        with (
            patch("app.services.contacts.get_contact", return_value=contact),
            pytest.raises(EddNotRequiredError),
        ):
            await approve_edd(mock_db, "t1", "contact-1", "senior-user-1")


@_skip_311
class TestInvoiceRiskRatingGuard:
    """authorise_invoice rejects contacts with risk_rating='unacceptable'."""

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
        contact_id: str = "contact-1",
    ) -> MagicMock:
        inv = MagicMock()
        inv.id = "inv-new"
        inv.tenant_id = "t1"
        inv.status = "draft"
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

    def _make_tenant(self) -> MagicMock:
        tenant = MagicMock()
        tenant.id = "t1"
        tenant.invoice_approval_threshold = None
        return tenant

    def _make_contact(
        self,
        *,
        risk_rating: str | None = None,
        credit_limit: str | None = None,
        edd_required: bool = False,
        edd_approved_by: str | None = None,
    ) -> MagicMock:
        contact = MagicMock()
        contact.id = "contact-1"
        contact.tenant_id = "t1"
        contact.credit_limit = Decimal(credit_limit) if credit_limit is not None else None
        contact.risk_rating = risk_rating
        contact.edd_required = edd_required
        contact.edd_approved_by = edd_approved_by
        return contact

    @pytest.mark.anyio
    async def test_unacceptable_rating_blocks_invoice(self, mock_db: AsyncMock) -> None:
        """Contact with risk_rating='unacceptable' blocks invoice authorisation."""
        from app.services.invoices import authorise_invoice

        inv = self._make_invoice()
        tenant = self._make_tenant()
        contact = self._make_contact(risk_rating="unacceptable", edd_required=True)

        with (
            patch("app.services.invoices.get_invoice", return_value=inv),
            patch("app.services.invoices.get_invoice_lines", return_value=[]),
            patch("app.services.invoices.get_tenant", return_value=tenant),
            patch("app.services.invoices.get_contact", return_value=contact),
            patch(
                "app.services.invoices._get_outstanding_invoice_total",
                return_value=Decimal("0"),
            ),
            pytest.raises(Exception, match="[Cc]ompliance|[Rr]estrict"),
        ):
            await authorise_invoice(mock_db, "t1", "inv-new", "actor-1")

    @pytest.mark.anyio
    async def test_high_rating_with_edd_approved_allows(self, mock_db: AsyncMock) -> None:
        """Contact with risk_rating='high' but EDD approved should pass."""
        from app.services.invoices import authorise_invoice

        inv = self._make_invoice()
        tenant = self._make_tenant()
        contact = self._make_contact(
            risk_rating="high",
            edd_required=True,
            edd_approved_by="senior-user-1",
        )

        with (
            patch("app.services.invoices.get_invoice", return_value=inv),
            patch("app.services.invoices.get_invoice_lines", return_value=[]),
            patch("app.services.invoices.get_tenant", return_value=tenant),
            patch("app.services.invoices.get_contact", return_value=contact),
            patch(
                "app.services.invoices._get_outstanding_invoice_total",
                return_value=Decimal("0"),
            ),
        ):
            result = await authorise_invoice(mock_db, "t1", "inv-new", "actor-1")

        assert result.status == "authorised"

    @pytest.mark.anyio
    async def test_high_rating_without_edd_blocks(self, mock_db: AsyncMock) -> None:
        """Contact with risk_rating='high' and edd_required=True but no EDD approval blocks."""
        from app.services.invoices import authorise_invoice

        inv = self._make_invoice()
        tenant = self._make_tenant()
        contact = self._make_contact(
            risk_rating="high",
            edd_required=True,
            edd_approved_by=None,
        )

        with (
            patch("app.services.invoices.get_invoice", return_value=inv),
            patch("app.services.invoices.get_invoice_lines", return_value=[]),
            patch("app.services.invoices.get_tenant", return_value=tenant),
            patch("app.services.invoices.get_contact", return_value=contact),
            patch(
                "app.services.invoices._get_outstanding_invoice_total",
                return_value=Decimal("0"),
            ),
            pytest.raises(Exception, match="[Ee]nhanced [Dd]ue [Dd]iligence|EDD"),
        ):
            await authorise_invoice(mock_db, "t1", "inv-new", "actor-1")

    @pytest.mark.anyio
    async def test_low_rating_allows_invoice(self, mock_db: AsyncMock) -> None:
        """Contact with risk_rating='low' should not be blocked."""
        from app.services.invoices import authorise_invoice

        inv = self._make_invoice()
        tenant = self._make_tenant()
        contact = self._make_contact(risk_rating="low")

        with (
            patch("app.services.invoices.get_invoice", return_value=inv),
            patch("app.services.invoices.get_invoice_lines", return_value=[]),
            patch("app.services.invoices.get_tenant", return_value=tenant),
            patch("app.services.invoices.get_contact", return_value=contact),
            patch(
                "app.services.invoices._get_outstanding_invoice_total",
                return_value=Decimal("0"),
            ),
        ):
            result = await authorise_invoice(mock_db, "t1", "inv-new", "actor-1")

        assert result.status == "authorised"

    @pytest.mark.anyio
    async def test_no_rating_allows_invoice(self, mock_db: AsyncMock) -> None:
        """Contact with no risk rating (None) should not be blocked."""
        from app.services.invoices import authorise_invoice

        inv = self._make_invoice()
        tenant = self._make_tenant()
        contact = self._make_contact(risk_rating=None)

        with (
            patch("app.services.invoices.get_invoice", return_value=inv),
            patch("app.services.invoices.get_invoice_lines", return_value=[]),
            patch("app.services.invoices.get_tenant", return_value=tenant),
            patch("app.services.invoices.get_contact", return_value=contact),
            patch(
                "app.services.invoices._get_outstanding_invoice_total",
                return_value=Decimal("0"),
            ),
        ):
            result = await authorise_invoice(mock_db, "t1", "inv-new", "actor-1")

        assert result.status == "authorised"


# ---------------------------------------------------------------------------
# Migration source inspection
# ---------------------------------------------------------------------------


class TestMigrationExists:
    """Migration 0023 adds risk rating columns to contacts."""

    def _read_migration_source(self) -> str:
        import pathlib

        mig_path = (
            pathlib.Path(__file__).resolve().parents[2]
            / "migrations"
            / "versions"
            / "0023_contacts_add_risk_rating.py"
        )
        return mig_path.read_text()

    def test_migration_file_exists(self) -> None:
        self._read_migration_source()

    def test_migration_adds_risk_rating_column(self) -> None:
        source = self._read_migration_source()
        assert "risk_rating" in source

    def test_migration_adds_edd_required_column(self) -> None:
        source = self._read_migration_source()
        assert "edd_required" in source

    def test_migration_has_downgrade(self) -> None:
        source = self._read_migration_source()
        assert "def downgrade()" in source

    def test_migration_downgrade_drops_columns(self) -> None:
        source = self._read_migration_source()
        # downgrade should drop each column
        assert source.count("drop_column") >= 7


# ---------------------------------------------------------------------------
# API endpoint source inspection
# ---------------------------------------------------------------------------


class TestRiskRatingEndpoint:
    """POST /v1/contacts/{id}/risk-rating endpoint exists."""

    def _read_contacts_api_source(self) -> str:
        import pathlib

        api_path = (
            pathlib.Path(__file__).resolve().parents[2] / "app" / "api" / "v1" / "contacts.py"
        )
        return api_path.read_text()

    def test_risk_rating_endpoint_exists(self) -> None:
        source = self._read_contacts_api_source()
        assert "risk-rating" in source or "risk_rating" in source

    def test_edd_approve_endpoint_exists(self) -> None:
        source = self._read_contacts_api_source()
        assert "edd" in source.lower()
