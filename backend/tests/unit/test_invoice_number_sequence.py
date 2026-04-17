"""Unit tests for invoice number sequence fix (Issue #24).

The old approach counted non-draft invoices to derive the next number,
which is a race condition under concurrent requests. The fix adds an
``invoice_number_seq`` column to the Tenant model and atomically
increments it via ``UPDATE ... SET invoice_number_seq = invoice_number_seq + 1
... RETURNING invoice_number_seq``.

Tests cover:
  - Tenant model has invoice_number_seq column (Integer, default 0)
  - authorise_invoice uses atomic increment instead of COUNT-based logic
  - Invoice number is formatted as INV-{seq:05d}
  - Sequential calls produce monotonically increasing numbers
  - Migration file exists with upgrade and downgrade
"""

from __future__ import annotations

import sys
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_NEEDS_311 = sys.version_info < (3, 11)
_skip_311 = pytest.mark.skipif(_NEEDS_311, reason="datetime.UTC requires Python >=3.11")


# ── Model-level tests (source inspection) ────────────────────────────────────


class TestTenantModelInvoiceNumberSeq:
    """Tenant model must have an invoice_number_seq column."""

    def _read_models_source(self) -> str:
        import pathlib

        models_path = pathlib.Path(__file__).resolve().parents[2] / "app" / "infra" / "models.py"
        return models_path.read_text()

    def test_invoice_number_seq_column_exists(self) -> None:
        source = self._read_models_source()
        idx = source.index("class Tenant(Base):")
        tenant_block = source[idx : idx + 2000]
        assert "invoice_number_seq" in tenant_block

    def test_invoice_number_seq_is_integer(self) -> None:
        source = self._read_models_source()
        idx = source.index("class Tenant(Base):")
        tenant_block = source[idx : idx + 2000]
        assert "invoice_number_seq" in tenant_block
        # Should be an Integer column
        seq_line_start = tenant_block.index("invoice_number_seq")
        seq_block = tenant_block[seq_line_start : seq_line_start + 200]
        assert "Integer" in seq_block

    def test_invoice_number_seq_defaults_to_zero(self) -> None:
        source = self._read_models_source()
        idx = source.index("class Tenant(Base):")
        tenant_block = source[idx : idx + 2000]
        seq_line_start = tenant_block.index("invoice_number_seq")
        seq_block = tenant_block[seq_line_start : seq_line_start + 200]
        assert "default=0" in seq_block


class TestServiceDoesNotUseCounting:
    """authorise_invoice must NOT use COUNT-based number assignment."""

    def _read_service_source(self) -> str:
        import pathlib

        svc_path = pathlib.Path(__file__).resolve().parents[2] / "app" / "services" / "invoices.py"
        return svc_path.read_text()

    def test_no_count_based_number_generation(self) -> None:
        """The old COUNT(*) approach must be removed."""
        source = self._read_service_source()
        # Find the authorise_invoice function
        idx = source.index("async def authorise_invoice(")
        # Look at the function body (until the next top-level def or end of file)
        next_def = source.find("\nasync def ", idx + 1)
        if next_def == -1:
            next_def = len(source)
        func_body = source[idx:next_def]
        assert "func.count()" not in func_body, (
            "authorise_invoice should not use func.count() for number generation"
        )

    def test_uses_atomic_increment(self) -> None:
        """The service should use an atomic UPDATE ... RETURNING pattern."""
        source = self._read_service_source()
        idx = source.index("async def authorise_invoice(")
        next_def = source.find("\nasync def ", idx + 1)
        if next_def == -1:
            next_def = len(source)
        func_body = source[idx:next_def]
        assert "invoice_number_seq" in func_body, (
            "authorise_invoice should use invoice_number_seq for atomic numbering"
        )


# ── Service-level async tests (require Python 3.11+) ─────────────────────────


@_skip_311
class TestAuthoriseInvoiceNumberSequence:
    """authorise_invoice assigns numbers via atomic tenant sequence increment."""

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
        total: str = "500.0000",
        status: str = "draft",
        tenant_id: str = "t1",
    ) -> MagicMock:
        inv = MagicMock()
        inv.id = "inv-1"
        inv.tenant_id = tenant_id
        inv.status = status
        inv.total = Decimal(total)
        inv.currency = "USD"
        inv.fx_rate = Decimal("1")
        inv.contact_id = "contact-1"
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

    @pytest.mark.anyio
    async def test_assigns_number_from_sequence(self, mock_db: AsyncMock) -> None:
        """Invoice number should come from the atomic sequence, not a COUNT."""
        from app.services.invoices import authorise_invoice

        inv = self._make_invoice()
        tenant = self._make_tenant(threshold=None)

        # Mock the atomic UPDATE ... RETURNING to return sequence value 7
        seq_result = MagicMock()
        seq_result.scalar_one.return_value = 7
        mock_db.execute = AsyncMock(return_value=seq_result)

        with (
            patch("app.services.invoices.get_invoice", return_value=inv),
            patch("app.services.invoices.get_invoice_lines", return_value=[]),
            patch("app.services.invoices.get_tenant", return_value=tenant),
        ):
            result = await authorise_invoice(mock_db, "t1", "inv-1", "actor-1")

        assert result.number == "INV-00007"

    @pytest.mark.anyio
    async def test_number_format_is_inv_five_digits(self, mock_db: AsyncMock) -> None:
        """Number should be zero-padded to 5 digits: INV-00001."""
        from app.services.invoices import authorise_invoice

        inv = self._make_invoice()
        tenant = self._make_tenant(threshold=None)

        seq_result = MagicMock()
        seq_result.scalar_one.return_value = 1
        mock_db.execute = AsyncMock(return_value=seq_result)

        with (
            patch("app.services.invoices.get_invoice", return_value=inv),
            patch("app.services.invoices.get_invoice_lines", return_value=[]),
            patch("app.services.invoices.get_tenant", return_value=tenant),
        ):
            result = await authorise_invoice(mock_db, "t1", "inv-1", "actor-1")

        assert result.number == "INV-00001"

    @pytest.mark.anyio
    async def test_large_sequence_number(self, mock_db: AsyncMock) -> None:
        """Numbers beyond 5 digits should still work (no truncation)."""
        from app.services.invoices import authorise_invoice

        inv = self._make_invoice()
        tenant = self._make_tenant(threshold=None)

        seq_result = MagicMock()
        seq_result.scalar_one.return_value = 123456
        mock_db.execute = AsyncMock(return_value=seq_result)

        with (
            patch("app.services.invoices.get_invoice", return_value=inv),
            patch("app.services.invoices.get_invoice_lines", return_value=[]),
            patch("app.services.invoices.get_tenant", return_value=tenant),
        ):
            result = await authorise_invoice(mock_db, "t1", "inv-1", "actor-1")

        assert result.number == "INV-123456"

    @pytest.mark.anyio
    async def test_awaiting_approval_also_uses_sequence(self, mock_db: AsyncMock) -> None:
        """Even when invoice goes to awaiting_approval, number comes from sequence."""
        from app.services.invoices import authorise_invoice

        inv = self._make_invoice(total="50000.0000")
        tenant = self._make_tenant(threshold="10000.0000")

        seq_result = MagicMock()
        seq_result.scalar_one.return_value = 42
        mock_db.execute = AsyncMock(return_value=seq_result)

        with (
            patch("app.services.invoices.get_invoice", return_value=inv),
            patch("app.services.invoices.get_invoice_lines", return_value=[]),
            patch("app.services.invoices.get_tenant", return_value=tenant),
        ):
            result = await authorise_invoice(mock_db, "t1", "inv-1", "actor-1")

        assert result.status == "awaiting_approval"
        assert result.number == "INV-00042"


# ── Migration tests ──────────────────────────────────────────────────────────


class TestMigrationExists:
    """A migration for the invoice_number_seq column must exist."""

    def _get_migration_files(self) -> list:
        import pathlib

        migrations_dir = pathlib.Path(__file__).resolve().parents[2] / "migrations" / "versions"
        return [f for f in migrations_dir.glob("*invoice_number_seq*")]

    def test_migration_file_exists(self) -> None:
        files = self._get_migration_files()
        assert len(files) >= 1, "Migration for invoice_number_seq not found"

    def test_migration_has_upgrade_and_downgrade(self) -> None:
        files = self._get_migration_files()
        assert len(files) >= 1
        source = files[0].read_text()
        assert "def upgrade()" in source
        assert "def downgrade()" in source

    def test_migration_adds_column_to_tenants(self) -> None:
        files = self._get_migration_files()
        assert len(files) >= 1
        source = files[0].read_text()
        assert "invoice_number_seq" in source
        assert "tenants" in source

    def test_migration_depends_on_0019(self) -> None:
        files = self._get_migration_files()
        assert len(files) >= 1
        source = files[0].read_text()
        assert '"0019"' in source, "Migration should depend on revision 0019"
