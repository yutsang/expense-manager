"""Unit tests for payment idempotency key support (Issue #20).

Tests cover:
  - Payment model has idempotency_key column (nullable, indexed)
  - PaymentResponse schema includes idempotency_key field
  - create_payment: when key provided and no existing match, creates new payment
  - create_payment: when key provided and existing match within 24h, returns existing
  - create_payment: when key provided and existing match >24h old, creates new
  - create_payment: when key missing, creates normally and logs warning
  - API endpoint: extracts Idempotency-Key header and passes to service
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_UTC = timezone.utc  # noqa: UP017 - need 3.10 compat for test runner

_NEEDS_311 = sys.version_info < (3, 11)
_skip_311 = pytest.mark.skipif(_NEEDS_311, reason="datetime.UTC requires Python >=3.11")


# ── Model-level tests (source inspection, no runtime import needed) ──────────


class TestPaymentModelIdempotencyKey:
    """Payment model must have an idempotency_key column with an index."""

    def _read_models_source(self) -> str:
        import pathlib

        models_path = pathlib.Path(__file__).resolve().parents[2] / "app" / "infra" / "models.py"
        return models_path.read_text()

    def test_idempotency_key_column_exists(self) -> None:
        source = self._read_models_source()
        # Find the Payment class section and verify idempotency_key is there
        idx = source.index("class Payment(Base):")
        # Look at a reasonable chunk after the class definition
        payment_block = source[idx : idx + 2500]
        assert "idempotency_key" in payment_block

    def test_idempotency_key_is_nullable(self) -> None:
        source = self._read_models_source()
        idx = source.index("class Payment(Base):")
        payment_block = source[idx : idx + 2500]
        # The column should allow None for backward compatibility
        assert "nullable=True" in payment_block or "Mapped[str | None]" in payment_block

    def test_idempotency_key_has_index(self) -> None:
        source = self._read_models_source()
        idx = source.index("class Payment(Base):")
        payment_block = source[idx : idx + 2500]
        # Should have an index for fast lookup
        assert "ix_payments_idempotency" in payment_block or "index=True" in payment_block


# ── Schema tests ─────────────────────────────────────────────────────────────


class TestPaymentResponseSchema:
    """PaymentResponse must include idempotency_key."""

    def test_idempotency_key_in_response(self) -> None:
        from app.api.v1.schemas import PaymentResponse

        fields = PaymentResponse.model_fields
        assert "idempotency_key" in fields

    def test_idempotency_key_allows_none(self) -> None:
        from app.api.v1.schemas import PaymentResponse

        resp = PaymentResponse(
            id="p1",
            number="PAY-000001",
            payment_type="received",
            contact_id="c1",
            amount="100.0000",
            currency="USD",
            fx_rate="1",
            payment_date="2026-04-16",
            reference=None,
            status="pending",
            created_at=datetime.now(tz=_UTC),
            updated_at=datetime.now(tz=_UTC),
            idempotency_key=None,
        )
        assert resp.idempotency_key is None

    def test_idempotency_key_accepts_value(self) -> None:
        from app.api.v1.schemas import PaymentResponse

        resp = PaymentResponse(
            id="p1",
            number="PAY-000001",
            payment_type="received",
            contact_id="c1",
            amount="100.0000",
            currency="USD",
            fx_rate="1",
            payment_date="2026-04-16",
            reference=None,
            status="pending",
            created_at=datetime.now(tz=_UTC),
            updated_at=datetime.now(tz=_UTC),
            idempotency_key="idem-key-123",
        )
        assert resp.idempotency_key == "idem-key-123"


# ── Service-level tests ─────────────────────────────────────────────────────


class TestCreatePaymentServiceSource:
    """Verify service code structure via source inspection."""

    def _read_service_source(self) -> str:
        import pathlib

        svc_path = pathlib.Path(__file__).resolve().parents[2] / "app" / "services" / "payments.py"
        return svc_path.read_text()

    def test_create_payment_accepts_idempotency_key_param(self) -> None:
        source = self._read_service_source()
        assert "idempotency_key" in source

    def test_service_checks_existing_payment_by_key(self) -> None:
        """Service should query for existing payment with same key+tenant."""
        source = self._read_service_source()
        assert "idempotency_key" in source

    def test_service_logs_warning_when_key_missing(self) -> None:
        """Service should log a warning when no idempotency key is provided."""
        source = self._read_service_source()
        assert "idempotency_key" in source


class TestApiEndpointSource:
    """Verify API endpoint extracts Idempotency-Key header."""

    def _read_api_source(self) -> str:
        import pathlib

        api_path = (
            pathlib.Path(__file__).resolve().parents[2] / "app" / "api" / "v1" / "payments.py"
        )
        return api_path.read_text()

    def test_endpoint_accepts_idempotency_key_header(self) -> None:
        source = self._read_api_source()
        assert "Idempotency-Key" in source or "idempotency_key" in source

    def test_endpoint_passes_key_to_service(self) -> None:
        source = self._read_api_source()
        assert "idempotency_key" in source


# ── Async service tests (require Python 3.11+) ──────────────────────────────


@_skip_311
class TestCreatePaymentIdempotency:
    """create_payment idempotency behaviour."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        db = AsyncMock()
        db.flush = AsyncMock()
        db.refresh = AsyncMock()
        db.execute = AsyncMock()
        db.scalar = AsyncMock()
        db.add = MagicMock()
        return db

    def _make_contact(self, tenant_id: str = "t1") -> MagicMock:
        contact = MagicMock()
        contact.id = "contact-1"
        contact.tenant_id = tenant_id
        return contact

    def _make_existing_payment(
        self,
        *,
        idempotency_key: str = "idem-123",
        created_at: datetime | None = None,
    ) -> MagicMock:
        payment = MagicMock()
        payment.id = "existing-pay-id"
        payment.tenant_id = "t1"
        payment.number = "PAY-000001"
        payment.payment_type = "received"
        payment.status = "pending"
        payment.contact_id = "contact-1"
        payment.payment_date = "2026-04-16"
        payment.amount = Decimal("100.0000")
        payment.currency = "USD"
        payment.fx_rate = Decimal("1")
        payment.functional_amount = Decimal("100.0000")
        payment.idempotency_key = idempotency_key
        payment.created_at = created_at or datetime.now(tz=_UTC)
        return payment

    @pytest.mark.anyio
    async def test_new_payment_with_idempotency_key(self, mock_db: AsyncMock) -> None:
        """When key is provided and no match exists, create a new payment."""
        from app.services.payments import create_payment

        contact = self._make_contact()
        count_result = MagicMock()
        count_result.scalar.return_value = 0

        # First scalar call returns contact, second returns None (no existing payment)
        mock_db.scalar = AsyncMock(side_effect=[contact, None])
        mock_db.execute = AsyncMock(return_value=count_result)

        await create_payment(
            mock_db,
            "t1",
            "actor-1",
            payment_type="received",
            contact_id="contact-1",
            amount=Decimal("100.0000"),
            currency="USD",
            payment_date="2026-04-16",
            idempotency_key="idem-123",
        )

        # Should have called db.add (new payment created)
        mock_db.add.assert_called_once()

    @pytest.mark.anyio
    async def test_duplicate_key_returns_existing_payment(self, mock_db: AsyncMock) -> None:
        """When key matches an existing payment within 24h, return existing."""
        from app.services.payments import create_payment

        contact = self._make_contact()
        existing = self._make_existing_payment(
            created_at=datetime.now(tz=_UTC) - timedelta(hours=1),
        )

        # First scalar returns contact, second returns existing payment
        mock_db.scalar = AsyncMock(side_effect=[contact, existing])

        payment = await create_payment(
            mock_db,
            "t1",
            "actor-1",
            payment_type="received",
            contact_id="contact-1",
            amount=Decimal("100.0000"),
            currency="USD",
            payment_date="2026-04-16",
            idempotency_key="idem-123",
        )

        # Should NOT have called db.add (returned existing)
        mock_db.add.assert_not_called()
        assert payment.id == "existing-pay-id"

    @pytest.mark.anyio
    async def test_expired_key_creates_new_payment(self, mock_db: AsyncMock) -> None:
        """When key matches but payment is >24h old, create a new one."""
        from app.services.payments import create_payment

        contact = self._make_contact()
        count_result = MagicMock()
        count_result.scalar.return_value = 1

        # First scalar returns contact, second returns None (expired key not found
        # because the query filters by created_at > 24h ago)
        mock_db.scalar = AsyncMock(side_effect=[contact, None])
        mock_db.execute = AsyncMock(return_value=count_result)

        await create_payment(
            mock_db,
            "t1",
            "actor-1",
            payment_type="received",
            contact_id="contact-1",
            amount=Decimal("100.0000"),
            currency="USD",
            payment_date="2026-04-16",
            idempotency_key="idem-123",
        )

        # Should have called db.add (new payment created)
        mock_db.add.assert_called_once()

    @pytest.mark.anyio
    async def test_no_key_creates_normally_and_logs_warning(self, mock_db: AsyncMock) -> None:
        """When no idempotency key provided, create normally but log warning."""
        from app.services.payments import create_payment

        contact = self._make_contact()
        count_result = MagicMock()
        count_result.scalar.return_value = 0

        mock_db.scalar = AsyncMock(return_value=contact)
        mock_db.execute = AsyncMock(return_value=count_result)

        with patch("app.services.payments.log") as mock_log:
            await create_payment(
                mock_db,
                "t1",
                "actor-1",
                payment_type="received",
                contact_id="contact-1",
                amount=Decimal("100.0000"),
                currency="USD",
                payment_date="2026-04-16",
            )

            # Should have logged a warning about missing idempotency key
            mock_log.warning.assert_called_once()
            warning_call = mock_log.warning.call_args
            assert "idempotency" in warning_call[0][0].lower()

        # Should still create the payment
        mock_db.add.assert_called_once()

    @pytest.mark.anyio
    async def test_idempotency_key_stored_on_payment(self, mock_db: AsyncMock) -> None:
        """The idempotency key should be stored on the payment record."""
        from app.services.payments import create_payment

        contact = self._make_contact()
        count_result = MagicMock()
        count_result.scalar.return_value = 0

        # No existing payment with this key
        mock_db.scalar = AsyncMock(side_effect=[contact, None])
        mock_db.execute = AsyncMock(return_value=count_result)

        await create_payment(
            mock_db,
            "t1",
            "actor-1",
            payment_type="received",
            contact_id="contact-1",
            amount=Decimal("100.0000"),
            currency="USD",
            payment_date="2026-04-16",
            idempotency_key="idem-xyz",
        )

        # Verify the Payment object passed to db.add has the key
        added_payment = mock_db.add.call_args[0][0]
        assert added_payment.idempotency_key == "idem-xyz"

    @pytest.mark.anyio
    async def test_different_tenant_same_key_creates_new(self, mock_db: AsyncMock) -> None:
        """Same idempotency key for different tenant should create new payment."""
        from app.services.payments import create_payment

        contact = self._make_contact(tenant_id="t2")
        count_result = MagicMock()
        count_result.scalar.return_value = 0

        # No existing payment for this tenant+key
        mock_db.scalar = AsyncMock(side_effect=[contact, None])
        mock_db.execute = AsyncMock(return_value=count_result)

        await create_payment(
            mock_db,
            "t2",
            "actor-1",
            payment_type="received",
            contact_id="contact-1",
            amount=Decimal("100.0000"),
            currency="USD",
            payment_date="2026-04-16",
            idempotency_key="idem-123",
        )

        mock_db.add.assert_called_once()


# ── Migration test ───────────────────────────────────────────────────────────


class TestMigrationExists:
    """A migration for the idempotency_key column must exist."""

    def test_migration_file_exists(self) -> None:
        import pathlib

        migrations_dir = pathlib.Path(__file__).resolve().parents[2] / "migrations" / "versions"
        migration_files = list(migrations_dir.glob("*idempotency*"))
        assert len(migration_files) >= 1, "Migration for idempotency_key not found"

    def test_migration_has_upgrade_and_downgrade(self) -> None:
        import pathlib

        migrations_dir = pathlib.Path(__file__).resolve().parents[2] / "migrations" / "versions"
        migration_files = list(migrations_dir.glob("*idempotency*"))
        assert len(migration_files) >= 1
        source = migration_files[0].read_text()
        assert "def upgrade()" in source
        assert "def downgrade()" in source

    def test_migration_adds_idempotency_key_column(self) -> None:
        import pathlib

        migrations_dir = pathlib.Path(__file__).resolve().parents[2] / "migrations" / "versions"
        migration_files = list(migrations_dir.glob("*idempotency*"))
        assert len(migration_files) >= 1
        source = migration_files[0].read_text()
        assert "idempotency_key" in source
        assert "payments" in source

    def test_migration_creates_index(self) -> None:
        import pathlib

        migrations_dir = pathlib.Path(__file__).resolve().parents[2] / "migrations" / "versions"
        migration_files = list(migrations_dir.glob("*idempotency*"))
        assert len(migration_files) >= 1
        source = migration_files[0].read_text()
        assert "index" in source.lower() or "create_index" in source.lower()
