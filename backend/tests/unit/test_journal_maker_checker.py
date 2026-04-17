"""Unit tests for journal entry maker-checker (Issue #43).

Tests cover:
  - JournalEntry model has submitted_by, submitted_at, approved_by, approved_at columns
  - JournalEntry status CHECK constraint includes 'awaiting_approval'
  - Tenant model has journal_approval_required flag
  - JournalResponse schema includes new fields
  - submit_journal service: moves draft -> awaiting_approval
  - submit_journal: rejects non-draft journals
  - approve_journal service: moves awaiting_approval -> posted
  - approve_journal: rejects self-approval (403 scenario: approver == preparer)
  - approve_journal: rejects non-awaiting_approval journals
  - approve_journal: sets posted_by to the approver, not the preparer
  - When journal_approval_required=False, post_journal still works directly
  - API endpoints: POST /journals/{id}/submit and POST /journals/{id}/approve
  - Migration exists with upgrade and downgrade
"""

from __future__ import annotations

import pathlib
import sys
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_UTC = timezone.utc  # noqa: UP017 - need 3.10 compat for test runner
_NEEDS_311 = sys.version_info < (3, 11)
_skip_311 = pytest.mark.skipif(_NEEDS_311, reason="datetime.UTC requires Python >=3.11")


# ── Model-level tests (source inspection) ────────────────────────────────────


class TestJournalEntryModelMakerChecker:
    """JournalEntry model must have submitted_by, submitted_at, approved_by, approved_at."""

    def _read_models_source(self) -> str:
        models_path = pathlib.Path(__file__).resolve().parents[2] / "app" / "infra" / "models.py"
        return models_path.read_text()

    def _get_je_block(self) -> str:
        source = self._read_models_source()
        idx = source.index("class JournalEntry(Base):")
        return source[idx : idx + 3000]

    def test_submitted_by_column_exists(self) -> None:
        je_block = self._get_je_block()
        assert "submitted_by" in je_block

    def test_submitted_at_column_exists(self) -> None:
        je_block = self._get_je_block()
        assert "submitted_at" in je_block

    def test_approved_by_column_exists(self) -> None:
        je_block = self._get_je_block()
        assert "approved_by" in je_block

    def test_approved_at_column_exists(self) -> None:
        je_block = self._get_je_block()
        assert "approved_at" in je_block

    def test_status_constraint_includes_awaiting_approval(self) -> None:
        je_block = self._get_je_block()
        assert "awaiting_approval" in je_block

    def test_submitted_by_is_nullable(self) -> None:
        je_block = self._get_je_block()
        # submitted_by should be nullable (only set when submitted)
        assert "submitted_by" in je_block
        # Mapped[str | None] indicates nullable
        lines = [ln for ln in je_block.split("\n") if "submitted_by" in ln]
        assert any("None" in ln or "nullable=True" in ln for ln in lines)


class TestTenantModelApprovalFlag:
    """Tenant model must have journal_approval_required boolean flag."""

    def _read_models_source(self) -> str:
        models_path = pathlib.Path(__file__).resolve().parents[2] / "app" / "infra" / "models.py"
        return models_path.read_text()

    def _get_tenant_block(self) -> str:
        source = self._read_models_source()
        idx = source.index("class Tenant(Base):")
        end = source.index("class User(Base):")
        return source[idx:end]

    def test_journal_approval_required_column_exists(self) -> None:
        tenant_block = self._get_tenant_block()
        assert "journal_approval_required" in tenant_block

    def test_journal_approval_required_is_boolean(self) -> None:
        tenant_block = self._get_tenant_block()
        lines = [ln for ln in tenant_block.split("\n") if "journal_approval_required" in ln]
        assert any("Boolean" in ln or "bool" in ln.lower() for ln in lines)

    def test_journal_approval_required_defaults_false(self) -> None:
        tenant_block = self._get_tenant_block()
        # Find the column definition block (may span multiple lines)
        idx = tenant_block.index("journal_approval_required")
        col_block = tenant_block[idx : idx + 200]
        assert "False" in col_block or "false" in col_block


# ── Schema tests ──────────────────────────────────────────────────────────────


class TestJournalResponseSchemaApproval:
    """JournalResponse must include approval-related fields."""

    def test_submitted_by_in_response(self) -> None:
        from app.api.v1.schemas import JournalResponse

        fields = JournalResponse.model_fields
        assert "submitted_by" in fields

    def test_submitted_at_in_response(self) -> None:
        from app.api.v1.schemas import JournalResponse

        fields = JournalResponse.model_fields
        assert "submitted_at" in fields

    def test_approved_by_in_response(self) -> None:
        from app.api.v1.schemas import JournalResponse

        fields = JournalResponse.model_fields
        assert "approved_by" in fields

    def test_approved_at_in_response(self) -> None:
        from app.api.v1.schemas import JournalResponse

        fields = JournalResponse.model_fields
        assert "approved_at" in fields

    def test_response_accepts_none_approval_fields(self) -> None:
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
            submitted_by=None,
            submitted_at=None,
            approved_by=None,
            approved_at=None,
        )
        assert resp.submitted_by is None
        assert resp.approved_by is None


# ── Service-level source tests ────────────────────────────────────────────────


class TestJournalServiceMakerCheckerSource:
    """Verify service code structure via source inspection."""

    def _read_service_source(self) -> str:
        svc_path = pathlib.Path(__file__).resolve().parents[2] / "app" / "services" / "journals.py"
        return svc_path.read_text()

    def test_submit_journal_function_exists(self) -> None:
        source = self._read_service_source()
        assert "async def submit_journal(" in source

    def test_approve_journal_function_exists(self) -> None:
        source = self._read_service_source()
        assert "async def approve_journal(" in source

    def test_self_approval_error_class_exists(self) -> None:
        source = self._read_service_source()
        assert "SelfApprovalError" in source

    def test_approve_journal_checks_self_approval(self) -> None:
        """approve_journal must guard against approver == preparer."""
        source = self._read_service_source()
        # Find the approve_journal function and check it references self-approval
        idx = source.index("async def approve_journal(")
        fn_block = source[idx : idx + 1500]
        assert "SelfApprovalError" in fn_block or "submitted_by" in fn_block


# ── API endpoint source tests ─────────────────────────────────────────────────


class TestJournalApiMakerCheckerSource:
    """Verify API endpoint structure via source inspection."""

    def _read_api_source(self) -> str:
        api_path = (
            pathlib.Path(__file__).resolve().parents[2] / "app" / "api" / "v1" / "journals.py"
        )
        return api_path.read_text()

    def test_submit_endpoint_exists(self) -> None:
        source = self._read_api_source()
        assert "/submit" in source

    def test_approve_endpoint_exists(self) -> None:
        source = self._read_api_source()
        assert "/approve" in source

    def test_approve_endpoint_returns_403_on_self_approval(self) -> None:
        """The approve endpoint should handle SelfApprovalError with 403."""
        source = self._read_api_source()
        assert "SelfApprovalError" in source
        assert "403" in source or "HTTP_403_FORBIDDEN" in source


# ── Async service tests ───────────────────────────────────────────────────────


@_skip_311
class TestSubmitJournal:
    """submit_journal moves draft -> awaiting_approval."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        db = AsyncMock()
        db.flush = AsyncMock()
        db.execute = AsyncMock()
        db.scalar = AsyncMock()
        db.add = MagicMock()
        return db

    def _make_draft_journal(self, *, created_by: str = "user-preparer") -> MagicMock:
        je = MagicMock()
        je.id = "je-1"
        je.tenant_id = "t1"
        je.number = "DRAFT-abcd1234"
        je.status = "draft"
        je.description = "Test journal"
        je.created_by = created_by
        je.version = 1
        return je

    @pytest.mark.anyio
    async def test_submit_draft_to_awaiting_approval(self, mock_db: AsyncMock) -> None:
        from app.services.journals import submit_journal

        je = self._make_draft_journal()
        result = MagicMock()
        result.scalar_one_or_none.return_value = je
        mock_db.execute = AsyncMock(return_value=result)

        with patch("app.services.journals.emit", new_callable=AsyncMock):
            submitted = await submit_journal(
                mock_db,
                journal_id="je-1",
                tenant_id="t1",
                actor_id="user-preparer",
            )

        assert submitted.status == "awaiting_approval"
        assert submitted.submitted_by == "user-preparer"
        assert submitted.submitted_at is not None

    @pytest.mark.anyio
    async def test_submit_non_draft_raises(self, mock_db: AsyncMock) -> None:
        from app.domain.ledger.journal import JournalStatusError
        from app.services.journals import submit_journal

        je = self._make_draft_journal()
        je.status = "posted"
        result = MagicMock()
        result.scalar_one_or_none.return_value = je
        mock_db.execute = AsyncMock(return_value=result)

        with pytest.raises(JournalStatusError):
            await submit_journal(
                mock_db,
                journal_id="je-1",
                tenant_id="t1",
                actor_id="user-preparer",
            )

    @pytest.mark.anyio
    async def test_submit_already_awaiting_raises(self, mock_db: AsyncMock) -> None:
        from app.domain.ledger.journal import JournalStatusError
        from app.services.journals import submit_journal

        je = self._make_draft_journal()
        je.status = "awaiting_approval"
        result = MagicMock()
        result.scalar_one_or_none.return_value = je
        mock_db.execute = AsyncMock(return_value=result)

        with pytest.raises(JournalStatusError):
            await submit_journal(
                mock_db,
                journal_id="je-1",
                tenant_id="t1",
                actor_id="user-preparer",
            )


@_skip_311
class TestApproveJournal:
    """approve_journal moves awaiting_approval -> posted."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        db = AsyncMock()
        db.flush = AsyncMock()
        db.execute = AsyncMock()
        db.scalar = AsyncMock()
        db.add = MagicMock()
        return db

    def _make_awaiting_journal(
        self,
        *,
        submitted_by: str = "user-preparer",
    ) -> MagicMock:
        je = MagicMock()
        je.id = "je-1"
        je.tenant_id = "t1"
        je.number = "DRAFT-abcd1234"
        je.status = "awaiting_approval"
        je.description = "Test journal"
        je.submitted_by = submitted_by
        je.submitted_at = datetime.now(tz=_UTC)
        je.created_by = submitted_by
        je.period_id = "p1"
        je.date = datetime.now(tz=_UTC)
        je.version = 1
        return je

    @pytest.mark.anyio
    async def test_approve_sets_posted_status(self, mock_db: AsyncMock) -> None:
        from app.services.journals import approve_journal

        je = self._make_awaiting_journal()
        result = MagicMock()
        result.scalar_one_or_none.return_value = je
        lines_result = MagicMock()
        lines_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(side_effect=[result, lines_result])

        with (
            patch("app.services.journals.emit", new_callable=AsyncMock),
            patch("app.services.journals.assert_can_post", new_callable=AsyncMock),
            patch("app.services.journals.validate_balance"),
            patch(
                "app.services.journals._next_number",
                new_callable=AsyncMock,
                return_value="JE-2026-0001",
            ),
        ):
            approved = await approve_journal(
                mock_db,
                journal_id="je-1",
                tenant_id="t1",
                actor_id="user-approver",
            )

        assert approved.status == "posted"

    @pytest.mark.anyio
    async def test_approve_sets_posted_by_to_approver(self, mock_db: AsyncMock) -> None:
        from app.services.journals import approve_journal

        je = self._make_awaiting_journal()
        result = MagicMock()
        result.scalar_one_or_none.return_value = je
        lines_result = MagicMock()
        lines_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(side_effect=[result, lines_result])

        with (
            patch("app.services.journals.emit", new_callable=AsyncMock),
            patch("app.services.journals.assert_can_post", new_callable=AsyncMock),
            patch("app.services.journals.validate_balance"),
            patch(
                "app.services.journals._next_number",
                new_callable=AsyncMock,
                return_value="JE-2026-0001",
            ),
        ):
            approved = await approve_journal(
                mock_db,
                journal_id="je-1",
                tenant_id="t1",
                actor_id="user-approver",
            )

        assert approved.posted_by == "user-approver"
        assert approved.approved_by == "user-approver"

    @pytest.mark.anyio
    async def test_approve_rejects_self_approval(self, mock_db: AsyncMock) -> None:
        from app.services.journals import SelfApprovalError, approve_journal

        je = self._make_awaiting_journal(submitted_by="same-user")
        result = MagicMock()
        result.scalar_one_or_none.return_value = je
        mock_db.execute = AsyncMock(return_value=result)

        with pytest.raises(SelfApprovalError):
            await approve_journal(
                mock_db,
                journal_id="je-1",
                tenant_id="t1",
                actor_id="same-user",  # same as submitted_by
            )

    @pytest.mark.anyio
    async def test_approve_non_awaiting_raises(self, mock_db: AsyncMock) -> None:
        from app.domain.ledger.journal import JournalStatusError
        from app.services.journals import approve_journal

        je = self._make_awaiting_journal()
        je.status = "draft"
        result = MagicMock()
        result.scalar_one_or_none.return_value = je
        mock_db.execute = AsyncMock(return_value=result)

        with pytest.raises(JournalStatusError):
            await approve_journal(
                mock_db,
                journal_id="je-1",
                tenant_id="t1",
                actor_id="user-approver",
            )

    @pytest.mark.anyio
    async def test_approve_posted_raises(self, mock_db: AsyncMock) -> None:
        from app.domain.ledger.journal import JournalStatusError
        from app.services.journals import approve_journal

        je = self._make_awaiting_journal()
        je.status = "posted"
        result = MagicMock()
        result.scalar_one_or_none.return_value = je
        mock_db.execute = AsyncMock(return_value=result)

        with pytest.raises(JournalStatusError):
            await approve_journal(
                mock_db,
                journal_id="je-1",
                tenant_id="t1",
                actor_id="user-approver",
            )


# ── Direct post still works when approval not required ─────────────────────


class TestPostJournalStillWorks:
    """post_journal should continue to work for draft -> posted (existing flow)."""

    def _read_service_source(self) -> str:
        svc_path = pathlib.Path(__file__).resolve().parents[2] / "app" / "services" / "journals.py"
        return svc_path.read_text()

    def test_post_journal_still_accepts_draft(self) -> None:
        """post_journal should still handle draft status."""
        source = self._read_service_source()
        idx = source.index("async def post_journal(")
        fn_block = source[idx : idx + 1500]
        assert "draft" in fn_block


# ── Migration tests ───────────────────────────────────────────────────────────


class TestMakerCheckerMigration:
    """A migration for the maker-checker columns must exist."""

    def _get_migration_files(self) -> list[pathlib.Path]:
        migrations_dir = pathlib.Path(__file__).resolve().parents[2] / "migrations" / "versions"
        return [f for f in migrations_dir.glob("*maker_checker*")]

    def test_migration_file_exists(self) -> None:
        migration_files = self._get_migration_files()
        assert len(migration_files) >= 1, "Migration for maker-checker not found"

    def test_migration_has_upgrade_and_downgrade(self) -> None:
        migration_files = self._get_migration_files()
        assert len(migration_files) >= 1
        source = migration_files[0].read_text()
        assert "def upgrade()" in source
        assert "def downgrade()" in source

    def test_migration_adds_submitted_by(self) -> None:
        migration_files = self._get_migration_files()
        assert len(migration_files) >= 1
        source = migration_files[0].read_text()
        assert "submitted_by" in source

    def test_migration_adds_approved_by(self) -> None:
        migration_files = self._get_migration_files()
        assert len(migration_files) >= 1
        source = migration_files[0].read_text()
        assert "approved_by" in source

    def test_migration_adds_journal_approval_required(self) -> None:
        migration_files = self._get_migration_files()
        assert len(migration_files) >= 1
        source = migration_files[0].read_text()
        assert "journal_approval_required" in source

    def test_migration_updates_status_constraint(self) -> None:
        migration_files = self._get_migration_files()
        assert len(migration_files) >= 1
        source = migration_files[0].read_text()
        assert "awaiting_approval" in source

    def test_migration_depends_on_0024(self) -> None:
        migration_files = self._get_migration_files()
        assert len(migration_files) >= 1
        source = migration_files[0].read_text()
        assert '"0024"' in source, "Migration should depend on revision 0024"
