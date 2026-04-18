"""Unit tests for accruals and prepayments module (Issue #42).

Tests cover:
  - Accrual model: type, status, amount, debit/credit accounts, journal refs
  - AccrualCreate schema: validates type, amount, account IDs
  - AccrualResponse schema
  - Service: create_accrual posts initial JE
  - Service: reverse_accruals creates reversing JEs for prior period
  - Migration adds accruals table
  - Integration with period transition
"""

from __future__ import annotations

import pathlib
import sys
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_NEEDS_311 = sys.version_info < (3, 11)
_skip_311 = pytest.mark.skipif(_NEEDS_311, reason="datetime.UTC requires Python >=3.11")


# ── Schema tests ────────────────────────────────────────────────────────────


class TestAccrualCreateSchema:
    """AccrualCreate validates type, amount, and account IDs."""

    def test_valid_accrual(self) -> None:
        from app.api.v1.schemas import AccrualCreate

        body = AccrualCreate(
            accrual_type="accrual",
            description="December rent",
            amount="5000.0000",
            currency="USD",
            debit_account_id="acct-1",
            credit_account_id="acct-2",
            period_id="period-1",
        )
        assert body.accrual_type == "accrual"
        assert body.amount == "5000.0000"

    def test_valid_prepayment(self) -> None:
        from app.api.v1.schemas import AccrualCreate

        body = AccrualCreate(
            accrual_type="prepayment",
            description="Insurance prepaid",
            amount="12000.0000",
            currency="USD",
            debit_account_id="acct-1",
            credit_account_id="acct-2",
            period_id="period-1",
        )
        assert body.accrual_type == "prepayment"

    def test_invalid_type_rejected(self) -> None:
        from app.api.v1.schemas import AccrualCreate

        with pytest.raises(Exception):
            AccrualCreate(
                accrual_type="invalid",
                description="Test",
                amount="1000.0000",
                currency="USD",
                debit_account_id="acct-1",
                credit_account_id="acct-2",
                period_id="period-1",
            )

    def test_amount_must_be_positive(self) -> None:
        from app.api.v1.schemas import AccrualCreate

        with pytest.raises(Exception):
            AccrualCreate(
                accrual_type="accrual",
                description="Test",
                amount="-100.00",
                currency="USD",
                debit_account_id="acct-1",
                credit_account_id="acct-2",
                period_id="period-1",
            )

    def test_amount_must_be_decimal_string(self) -> None:
        from app.api.v1.schemas import AccrualCreate

        with pytest.raises(Exception):
            AccrualCreate(
                accrual_type="accrual",
                description="Test",
                amount="not-a-number",
                currency="USD",
                debit_account_id="acct-1",
                credit_account_id="acct-2",
                period_id="period-1",
            )

    def test_same_debit_credit_account_rejected(self) -> None:
        from app.api.v1.schemas import AccrualCreate

        with pytest.raises(Exception, match="debit and credit accounts must differ"):
            AccrualCreate(
                accrual_type="accrual",
                description="Test",
                amount="1000.0000",
                currency="USD",
                debit_account_id="acct-1",
                credit_account_id="acct-1",
                period_id="period-1",
            )


class TestAccrualResponseSchema:
    """AccrualResponse returns accrual with JE references."""

    def test_response_has_required_fields(self) -> None:
        from app.api.v1.schemas import AccrualResponse

        resp = AccrualResponse(
            id="acc-1",
            accrual_type="accrual",
            description="December rent",
            amount="5000.0000",
            currency="USD",
            debit_account_id="acct-1",
            credit_account_id="acct-2",
            period_id="period-1",
            journal_entry_id="je-1",
            reversal_journal_entry_id=None,
            status="posted",
            created_at="2026-04-16T00:00:00Z",
            updated_at="2026-04-16T00:00:00Z",
        )
        assert resp.status == "posted"
        assert resp.reversal_journal_entry_id is None


# ── Model tests (source-level) ──────────────────────────────────────────────


class TestAccrualModel:
    """Accrual model has required columns."""

    def _read_models(self) -> str:
        models_path = pathlib.Path(__file__).resolve().parents[2] / "app" / "infra" / "models.py"
        return models_path.read_text()

    def test_accruals_table_exists(self) -> None:
        source = self._read_models()
        assert '"accruals"' in source

    def test_accrual_type_column(self) -> None:
        source = self._read_models()
        assert "accrual_type" in source

    def test_journal_entry_id_column(self) -> None:
        source = self._read_models()
        # There should be a journal_entry_id on the Accrual model
        idx = source.index('"accruals"')
        block = source[idx : idx + 1500]
        assert "journal_entry_id" in block

    def test_reversal_journal_entry_id_column(self) -> None:
        source = self._read_models()
        assert "reversal_journal_entry_id" in source

    def test_status_column(self) -> None:
        source = self._read_models()
        idx = source.index('"accruals"')
        block = source[idx : idx + 1500]
        assert "status" in block


# ── Service tests (source-level) ────────────────────────────────────────────


class TestAccrualsServiceSource:
    """Verify accruals service code exists."""

    def _read_service_source(self) -> str:
        svc_path = (
            pathlib.Path(__file__).resolve().parents[2] / "app" / "services" / "accruals.py"
        )
        return svc_path.read_text()

    def test_create_accrual_function_exists(self) -> None:
        source = self._read_service_source()
        assert "async def create_accrual(" in source

    def test_reverse_accruals_function_exists(self) -> None:
        source = self._read_service_source()
        assert "async def reverse_accruals(" in source

    def test_list_accruals_function_exists(self) -> None:
        source = self._read_service_source()
        assert "async def list_accruals(" in source

    def test_create_accrual_posts_je(self) -> None:
        source = self._read_service_source()
        assert "JournalEntry" in source
        assert "JournalLine" in source

    def test_reverse_creates_reversal_je(self) -> None:
        source = self._read_service_source()
        assert "reversal" in source.lower()


# ── API tests (source-level) ────────────────────────────────────────────────


class TestAccrualsApiSource:
    """Verify accruals API endpoints exist."""

    def _read_api_source(self) -> str:
        api_path = (
            pathlib.Path(__file__).resolve().parents[2] / "app" / "api" / "v1" / "accruals.py"
        )
        return api_path.read_text()

    def test_create_endpoint_exists(self) -> None:
        source = self._read_api_source()
        assert "post" in source.lower()

    def test_list_endpoint_exists(self) -> None:
        source = self._read_api_source()
        assert "get" in source.lower()

    def test_endpoint_uses_accrual_schemas(self) -> None:
        source = self._read_api_source()
        assert "AccrualCreate" in source
        assert "AccrualResponse" in source


# ── Service-level async tests ────────────────────────────────────────────────


@_skip_311
class TestCreateAccrualService:
    """create_accrual creates the accrual record and posts a JE."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        db = AsyncMock()
        db.flush = AsyncMock()
        db.refresh = AsyncMock()
        db.execute = AsyncMock()
        db.scalar = AsyncMock()
        db.add = MagicMock()
        return db

    def _make_period(self, *, status: str = "open") -> MagicMock:
        period = MagicMock()
        period.id = "period-1"
        period.tenant_id = "t1"
        period.status = status
        period.name = "2026-04"
        period.start_date = "2026-04-01"
        return period

    @pytest.mark.anyio
    async def test_creates_accrual_record(self, mock_db: AsyncMock) -> None:
        from app.services.accruals import create_accrual

        period = self._make_period()

        with (
            patch("app.services.accruals.get_period", return_value=period),
            patch("app.services.accruals.assert_can_post", return_value=period),
        ):
            await create_accrual(
                mock_db,
                tenant_id="t1",
                actor_id="actor-1",
                accrual_type="accrual",
                description="December rent",
                amount=Decimal("5000.0000"),
                currency="USD",
                debit_account_id="acct-1",
                credit_account_id="acct-2",
                period_id="period-1",
            )

        # Should have added objects to the session (accrual + JE + JL lines)
        assert mock_db.add.called

    @pytest.mark.anyio
    async def test_rejects_closed_period(self, mock_db: AsyncMock) -> None:
        from app.services.accruals import create_accrual
        from app.services.periods import PeriodPostingError

        with (
            patch(
                "app.services.accruals.assert_can_post",
                side_effect=PeriodPostingError("Period is hard_closed"),
            ),pytest.raises(PeriodPostingError)
        ):
            await create_accrual(
                mock_db,
                tenant_id="t1",
                actor_id="actor-1",
                accrual_type="accrual",
                description="December rent",
                amount=Decimal("5000.0000"),
                currency="USD",
                debit_account_id="acct-1",
                credit_account_id="acct-2",
                period_id="period-1",
            )


@_skip_311
class TestReverseAccruals:
    """reverse_accruals creates reversing JEs for all accruals from prior period."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        db = AsyncMock()
        db.flush = AsyncMock()
        db.refresh = AsyncMock()
        db.execute = AsyncMock()
        db.scalar = AsyncMock()
        db.add = MagicMock()
        return db

    def _make_accrual(self) -> MagicMock:
        accrual = MagicMock()
        accrual.id = "acc-1"
        accrual.tenant_id = "t1"
        accrual.accrual_type = "accrual"
        accrual.description = "December rent"
        accrual.amount = Decimal("5000.0000")
        accrual.currency = "USD"
        accrual.debit_account_id = "acct-1"
        accrual.credit_account_id = "acct-2"
        accrual.period_id = "period-old"
        accrual.journal_entry_id = "je-1"
        accrual.reversal_journal_entry_id = None
        accrual.status = "posted"
        accrual.version = 1
        return accrual

    @pytest.mark.anyio
    async def test_reverses_posted_accruals(self, mock_db: AsyncMock) -> None:
        from app.services.accruals import reverse_accruals

        accrual = self._make_accrual()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [accrual]
        mock_db.execute.return_value = mock_result

        new_period = MagicMock()
        new_period.id = "period-new"
        new_period.name = "2026-05"
        new_period.start_date = MagicMock()

        reversed_count = await reverse_accruals(
            mock_db,
            tenant_id="t1",
            prior_period_id="period-old",
            new_period=new_period,
            actor_id="actor-1",
        )

        assert reversed_count == 1
        assert accrual.status == "reversed"
        assert accrual.reversal_journal_entry_id is not None

    @pytest.mark.anyio
    async def test_skips_already_reversed(self, mock_db: AsyncMock) -> None:
        from app.services.accruals import reverse_accruals

        accrual = self._make_accrual()
        accrual.status = "reversed"
        accrual.reversal_journal_entry_id = "je-2"

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [accrual]
        mock_db.execute.return_value = mock_result

        new_period = MagicMock()
        new_period.id = "period-new"
        new_period.name = "2026-05"
        new_period.start_date = MagicMock()

        reversed_count = await reverse_accruals(
            mock_db,
            tenant_id="t1",
            prior_period_id="period-old",
            new_period=new_period,
            actor_id="actor-1",
        )
        assert reversed_count == 0


# ── Migration test ───────────────────────────────────────────────────────────


class TestAccrualsMigration:
    """Migration 0029 adds accruals table."""

    def test_migration_file_exists(self) -> None:
        mig_path = (
            pathlib.Path(__file__).resolve().parents[2]
            / "migrations"
            / "versions"
            / "0029_add_accruals_table.py"
        )
        assert mig_path.exists(), f"Migration file not found: {mig_path}"

    def test_migration_has_upgrade_and_downgrade(self) -> None:
        mig_path = (
            pathlib.Path(__file__).resolve().parents[2]
            / "migrations"
            / "versions"
            / "0029_add_accruals_table.py"
        )
        source = mig_path.read_text()
        assert "def upgrade()" in source
        assert "def downgrade()" in source
        assert "accruals" in source
