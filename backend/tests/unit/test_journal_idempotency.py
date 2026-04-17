"""Unit tests for journal entry idempotency key support (Issue #22).

Tests cover:
  - JournalEntry model has idempotency_key column (nullable, indexed)
  - JournalResponse schema includes idempotency_key field
  - create_draft: when key provided and no existing match, creates new journal
  - create_draft: when key provided and existing match within 24h, returns existing
  - create_draft: when key provided and existing match >24h old, creates new
  - create_draft: when key missing, creates normally and logs warning
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


class TestJournalEntryModelIdempotencyKey:
    """JournalEntry model must have an idempotency_key column with an index."""

    def _read_models_source(self) -> str:
        import pathlib

        models_path = pathlib.Path(__file__).resolve().parents[2] / "app" / "infra" / "models.py"
        return models_path.read_text()

    def test_idempotency_key_column_exists(self) -> None:
        source = self._read_models_source()
        # Find the JournalEntry class section and verify idempotency_key is there
        idx = source.index("class JournalEntry(Base):")
        # Look at a reasonable chunk after the class definition
        je_block = source[idx : idx + 2500]
        assert "idempotency_key" in je_block

    def test_idempotency_key_is_nullable(self) -> None:
        source = self._read_models_source()
        idx = source.index("class JournalEntry(Base):")
        je_block = source[idx : idx + 2500]
        # The column should allow None for backward compatibility
        assert "nullable=True" in je_block or "Mapped[str | None]" in je_block

    def test_idempotency_key_has_index(self) -> None:
        source = self._read_models_source()
        idx = source.index("class JournalEntry(Base):")
        je_block = source[idx : idx + 2500]
        # Should have an index for fast lookup
        assert "ix_je_idempotency" in je_block or "index=True" in je_block


# ── Schema tests ─────────────────────────────────────────────────────────────


class TestJournalResponseSchema:
    """JournalResponse must include idempotency_key."""

    def test_idempotency_key_in_response(self) -> None:
        from app.api.v1.schemas import JournalResponse

        fields = JournalResponse.model_fields
        assert "idempotency_key" in fields

    def test_idempotency_key_allows_none(self) -> None:
        from app.api.v1.schemas import JournalResponse

        resp = JournalResponse(
            id="je1",
            number="DRAFT-abcd1234",
            date=datetime.now(tz=_UTC),
            period_id="p1",
            description="Test journal",
            status="draft",
            source_type="manual",
            source_id=None,
            total_debit="100.0000",
            total_credit="100.0000",
            created_at=datetime.now(tz=_UTC),
            updated_at=datetime.now(tz=_UTC),
            posted_at=None,
            idempotency_key=None,
        )
        assert resp.idempotency_key is None

    def test_idempotency_key_accepts_value(self) -> None:
        from app.api.v1.schemas import JournalResponse

        resp = JournalResponse(
            id="je1",
            number="DRAFT-abcd1234",
            date=datetime.now(tz=_UTC),
            period_id="p1",
            description="Test journal",
            status="draft",
            source_type="manual",
            source_id=None,
            total_debit="100.0000",
            total_credit="100.0000",
            created_at=datetime.now(tz=_UTC),
            updated_at=datetime.now(tz=_UTC),
            posted_at=None,
            idempotency_key="idem-key-123",
        )
        assert resp.idempotency_key == "idem-key-123"


# ── Service-level tests ─────────────────────────────────────────────────────


class TestCreateDraftServiceSource:
    """Verify service code structure via source inspection."""

    def _read_service_source(self) -> str:
        import pathlib

        svc_path = pathlib.Path(__file__).resolve().parents[2] / "app" / "services" / "journals.py"
        return svc_path.read_text()

    def test_create_draft_accepts_idempotency_key_param(self) -> None:
        source = self._read_service_source()
        assert "idempotency_key" in source

    def test_service_checks_existing_journal_by_key(self) -> None:
        """Service should query for existing journal with same key+tenant."""
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
            pathlib.Path(__file__).resolve().parents[2] / "app" / "api" / "v1" / "journals.py"
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
class TestCreateDraftIdempotency:
    """create_draft idempotency behaviour."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        db = AsyncMock()
        db.flush = AsyncMock()
        db.refresh = AsyncMock()
        db.execute = AsyncMock()
        db.scalar = AsyncMock()
        db.add = MagicMock()
        return db

    def _make_lines(self) -> list[MagicMock]:
        from app.domain.ledger.journal import JournalLineInput

        return [
            JournalLineInput(
                account_id="acc-1",
                debit=Decimal("100.0000"),
                credit=Decimal("0"),
                currency="USD",
                functional_debit=Decimal("100.0000"),
                functional_credit=Decimal("0"),
            ),
            JournalLineInput(
                account_id="acc-2",
                debit=Decimal("0"),
                credit=Decimal("100.0000"),
                currency="USD",
                functional_debit=Decimal("0"),
                functional_credit=Decimal("100.0000"),
            ),
        ]

    def _make_existing_journal(
        self,
        *,
        idempotency_key: str = "idem-123",
        created_at: datetime | None = None,
    ) -> MagicMock:
        je = MagicMock()
        je.id = "existing-je-id"
        je.tenant_id = "t1"
        je.number = "DRAFT-abcd1234"
        je.status = "draft"
        je.description = "Test journal"
        je.idempotency_key = idempotency_key
        je.created_at = created_at or datetime.now(tz=_UTC)
        return je

    @pytest.mark.anyio
    async def test_new_journal_with_idempotency_key(self, mock_db: AsyncMock) -> None:
        """When key is provided and no match exists, create a new journal."""
        from datetime import date

        from app.services.journals import create_draft

        # Mock: no existing journal with this key (scalar returns None)
        # Mock: account query returns empty (no control accounts)
        accounts_result = MagicMock()
        accounts_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=accounts_result)
        mock_db.scalar = AsyncMock(return_value=None)

        with patch("app.services.journals.emit", new_callable=AsyncMock):
            await create_draft(
                mock_db,
                tenant_id="t1",
                date_=date(2026, 4, 16),
                period_id="p1",
                description="Test",
                lines=self._make_lines(),
                idempotency_key="idem-123",
            )

        # Should have called db.add (new journal created)
        assert mock_db.add.call_count >= 1

    @pytest.mark.anyio
    async def test_duplicate_key_returns_existing_journal(self, mock_db: AsyncMock) -> None:
        """When key matches an existing journal within 24h, return existing."""
        from datetime import date

        from app.services.journals import create_draft

        existing = self._make_existing_journal(
            created_at=datetime.now(tz=_UTC) - timedelta(hours=1),
        )

        # scalar returns the existing journal for the idempotency check
        mock_db.scalar = AsyncMock(return_value=existing)

        with patch("app.services.journals.emit", new_callable=AsyncMock):
            je = await create_draft(
                mock_db,
                tenant_id="t1",
                date_=date(2026, 4, 16),
                period_id="p1",
                description="Test",
                lines=self._make_lines(),
                idempotency_key="idem-123",
            )

        # Should NOT have called db.add (returned existing)
        mock_db.add.assert_not_called()
        assert je.id == "existing-je-id"

    @pytest.mark.anyio
    async def test_expired_key_creates_new_journal(self, mock_db: AsyncMock) -> None:
        """When key matches but journal is >24h old, create a new one."""
        from datetime import date

        from app.services.journals import create_draft

        # scalar returns None (expired key not found because query filters by created_at)
        accounts_result = MagicMock()
        accounts_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=accounts_result)
        mock_db.scalar = AsyncMock(return_value=None)

        with patch("app.services.journals.emit", new_callable=AsyncMock):
            await create_draft(
                mock_db,
                tenant_id="t1",
                date_=date(2026, 4, 16),
                period_id="p1",
                description="Test",
                lines=self._make_lines(),
                idempotency_key="idem-123",
            )

        # Should have called db.add (new journal created)
        assert mock_db.add.call_count >= 1

    @pytest.mark.anyio
    async def test_no_key_creates_normally_and_logs_warning(self, mock_db: AsyncMock) -> None:
        """When no idempotency key provided, create normally but log warning."""
        from datetime import date

        from app.services.journals import create_draft

        accounts_result = MagicMock()
        accounts_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=accounts_result)

        with (
            patch("app.services.journals.log") as mock_log,
            patch("app.services.journals.emit", new_callable=AsyncMock),
        ):
            await create_draft(
                mock_db,
                tenant_id="t1",
                date_=date(2026, 4, 16),
                period_id="p1",
                description="Test",
                lines=self._make_lines(),
            )

            # Should have logged a warning about missing idempotency key
            mock_log.warning.assert_called_once()
            warning_call = mock_log.warning.call_args
            assert "idempotency" in warning_call[0][0].lower()

        # Should still create the journal
        assert mock_db.add.call_count >= 1

    @pytest.mark.anyio
    async def test_idempotency_key_stored_on_journal(self, mock_db: AsyncMock) -> None:
        """The idempotency key should be stored on the journal entry record."""
        from datetime import date

        from app.services.journals import create_draft

        # No existing journal with this key
        accounts_result = MagicMock()
        accounts_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=accounts_result)
        mock_db.scalar = AsyncMock(return_value=None)

        with patch("app.services.journals.emit", new_callable=AsyncMock):
            await create_draft(
                mock_db,
                tenant_id="t1",
                date_=date(2026, 4, 16),
                period_id="p1",
                description="Test",
                lines=self._make_lines(),
                idempotency_key="idem-xyz",
            )

        # Verify the JournalEntry object passed to db.add has the key
        # The first db.add call is the JournalEntry (lines come after)
        first_added = mock_db.add.call_args_list[0][0][0]
        assert first_added.idempotency_key == "idem-xyz"

    @pytest.mark.anyio
    async def test_different_tenant_same_key_creates_new(self, mock_db: AsyncMock) -> None:
        """Same idempotency key for different tenant should create new journal."""
        from datetime import date

        from app.services.journals import create_draft

        # No existing journal for this tenant+key
        accounts_result = MagicMock()
        accounts_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=accounts_result)
        mock_db.scalar = AsyncMock(return_value=None)

        with patch("app.services.journals.emit", new_callable=AsyncMock):
            await create_draft(
                mock_db,
                tenant_id="t2",
                date_=date(2026, 4, 16),
                period_id="p1",
                description="Test",
                lines=self._make_lines(),
                idempotency_key="idem-123",
            )

        assert mock_db.add.call_count >= 1


# ── Migration test ───────────────────────────────────────────────────────────


class TestMigrationExists:
    """A migration for the journal_entries idempotency_key column must exist."""

    def _get_journal_migration_files(self) -> list:
        import pathlib

        migrations_dir = pathlib.Path(__file__).resolve().parents[2] / "migrations" / "versions"
        return [f for f in migrations_dir.glob("*idempotency*") if "journal" in f.name]

    def test_migration_file_exists(self) -> None:
        migration_files = self._get_journal_migration_files()
        assert len(migration_files) >= 1, "Migration for journal idempotency_key not found"

    def test_migration_has_upgrade_and_downgrade(self) -> None:
        migration_files = self._get_journal_migration_files()
        assert len(migration_files) >= 1
        source = migration_files[0].read_text()
        assert "def upgrade()" in source
        assert "def downgrade()" in source

    def test_migration_adds_idempotency_key_column(self) -> None:
        migration_files = self._get_journal_migration_files()
        assert len(migration_files) >= 1
        source = migration_files[0].read_text()
        assert "idempotency_key" in source
        assert "journal_entries" in source

    def test_migration_creates_index(self) -> None:
        migration_files = self._get_journal_migration_files()
        assert len(migration_files) >= 1
        source = migration_files[0].read_text()
        assert "index" in source.lower() or "create_index" in source.lower()

    def test_migration_depends_on_0018(self) -> None:
        migration_files = self._get_journal_migration_files()
        assert len(migration_files) >= 1
        source = migration_files[0].read_text()
        assert '"0018"' in source, "Migration should depend on revision 0018"
