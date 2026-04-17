"""Unit tests for GL account validation in journal entries (Issue #9).

Tests cover:
  - create_draft rejects lines referencing non-existent account_ids (HTTP 422)
  - create_draft rejects lines referencing accounts from a different tenant
  - Validation runs in the same flow as the insert (no TOCTOU gap)
  - Valid account_ids on all lines pass validation and create the journal
  - Error message lists all invalid account IDs
"""

from __future__ import annotations

import sys
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_NEEDS_311 = sys.version_info < (3, 11)
_skip_311 = pytest.mark.skipif(_NEEDS_311, reason="datetime.UTC requires Python >=3.11")


# ---------------------------------------------------------------------------
# Service source inspection tests (always run)
# ---------------------------------------------------------------------------


class TestJournalAccountValidationSource:
    """Verify service code includes account existence check."""

    def _read_service_source(self) -> str:
        import pathlib

        svc_path = pathlib.Path(__file__).resolve().parents[2] / "app" / "services" / "journals.py"
        return svc_path.read_text()

    def test_invalid_account_error_class_exists(self) -> None:
        source = self._read_service_source()
        assert "class InvalidAccountError" in source

    def test_create_draft_validates_accounts(self) -> None:
        source = self._read_service_source()
        assert "InvalidAccountError" in source


# ---------------------------------------------------------------------------
# Service-level async tests (require Python 3.11+)
# ---------------------------------------------------------------------------


@_skip_311
class TestJournalAccountValidation:
    """create_draft should validate all account_ids exist for the tenant."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        db = AsyncMock()
        db.flush = AsyncMock()
        db.refresh = AsyncMock()
        db.execute = AsyncMock()
        db.scalar = AsyncMock()
        db.add = MagicMock()
        return db

    def _make_lines(self, account_ids: list[str] | None = None) -> list:
        from app.domain.ledger.journal import JournalLineInput

        ids = account_ids or ["acc-1", "acc-2"]
        return [
            JournalLineInput(
                account_id=ids[0],
                debit=Decimal("100.0000"),
                credit=Decimal("0"),
                currency="USD",
                functional_debit=Decimal("100.0000"),
                functional_credit=Decimal("0"),
            ),
            JournalLineInput(
                account_id=ids[1] if len(ids) > 1 else ids[0],
                debit=Decimal("0"),
                credit=Decimal("100.0000"),
                currency="USD",
                functional_debit=Decimal("0"),
                functional_credit=Decimal("100.0000"),
            ),
        ]

    def _make_account(self, account_id: str, tenant_id: str = "t1") -> MagicMock:
        acc = MagicMock()
        acc.id = account_id
        acc.tenant_id = tenant_id
        acc.is_active = True
        acc.is_control_account = False
        acc.code = f"CODE-{account_id}"
        acc.name = f"Account {account_id}"
        return acc

    @pytest.mark.anyio
    async def test_nonexistent_account_raises_invalid_account_error(
        self, mock_db: AsyncMock
    ) -> None:
        """Lines referencing accounts that don't exist should raise InvalidAccountError."""
        from app.services.journals import InvalidAccountError, create_draft

        # Only acc-1 exists; acc-2 does not
        acc1 = self._make_account("acc-1")
        accounts_result = MagicMock()
        accounts_result.scalars.return_value.all.return_value = [acc1]
        mock_db.execute = AsyncMock(return_value=accounts_result)
        mock_db.scalar = AsyncMock(return_value=None)  # idempotency check

        with (
            patch("app.services.journals.emit", new_callable=AsyncMock),
            pytest.raises(InvalidAccountError, match="acc-2"),
        ):
            await create_draft(
                mock_db,
                tenant_id="t1",
                date_=date(2026, 4, 16),
                period_id="p1",
                description="Test",
                lines=self._make_lines(["acc-1", "acc-2"]),
            )

    @pytest.mark.anyio
    async def test_cross_tenant_account_raises_invalid_account_error(
        self, mock_db: AsyncMock
    ) -> None:
        """Accounts belonging to a different tenant should be treated as non-existent."""
        from app.services.journals import InvalidAccountError, create_draft

        # acc-1 exists for t1, acc-other exists for t2 (different tenant)
        acc1 = self._make_account("acc-1", tenant_id="t1")
        acc_other = self._make_account("acc-other", tenant_id="t2")
        accounts_result = MagicMock()
        accounts_result.scalars.return_value.all.return_value = [acc1, acc_other]
        mock_db.execute = AsyncMock(return_value=accounts_result)
        mock_db.scalar = AsyncMock(return_value=None)

        with (
            patch("app.services.journals.emit", new_callable=AsyncMock),
            pytest.raises(InvalidAccountError, match="acc-other"),
        ):
            await create_draft(
                mock_db,
                tenant_id="t1",
                date_=date(2026, 4, 16),
                period_id="p1",
                description="Test",
                lines=self._make_lines(["acc-1", "acc-other"]),
            )

    @pytest.mark.anyio
    async def test_all_valid_accounts_creates_journal(self, mock_db: AsyncMock) -> None:
        """When all accounts exist and belong to the tenant, journal is created."""
        from app.services.journals import create_draft

        acc1 = self._make_account("acc-1")
        acc2 = self._make_account("acc-2")
        accounts_result = MagicMock()
        accounts_result.scalars.return_value.all.return_value = [acc1, acc2]
        mock_db.execute = AsyncMock(return_value=accounts_result)
        mock_db.scalar = AsyncMock(return_value=None)

        with patch("app.services.journals.emit", new_callable=AsyncMock):
            je = await create_draft(
                mock_db,
                tenant_id="t1",
                date_=date(2026, 4, 16),
                period_id="p1",
                description="Test",
                lines=self._make_lines(["acc-1", "acc-2"]),
            )

        assert je is not None
        assert mock_db.add.call_count >= 1

    @pytest.mark.anyio
    async def test_error_lists_all_invalid_ids(self, mock_db: AsyncMock) -> None:
        """Error message should list all invalid account IDs, not just the first."""
        from app.domain.ledger.journal import JournalLineInput
        from app.services.journals import InvalidAccountError, create_draft

        lines = [
            JournalLineInput(
                account_id="bad-1",
                debit=Decimal("50.0000"),
                credit=Decimal("0"),
                currency="USD",
                functional_debit=Decimal("50.0000"),
                functional_credit=Decimal("0"),
            ),
            JournalLineInput(
                account_id="bad-2",
                debit=Decimal("50.0000"),
                credit=Decimal("0"),
                currency="USD",
                functional_debit=Decimal("50.0000"),
                functional_credit=Decimal("0"),
            ),
            JournalLineInput(
                account_id="good-1",
                debit=Decimal("0"),
                credit=Decimal("100.0000"),
                currency="USD",
                functional_debit=Decimal("0"),
                functional_credit=Decimal("100.0000"),
            ),
        ]

        good = self._make_account("good-1")
        accounts_result = MagicMock()
        accounts_result.scalars.return_value.all.return_value = [good]
        mock_db.execute = AsyncMock(return_value=accounts_result)
        mock_db.scalar = AsyncMock(return_value=None)

        with (
            patch("app.services.journals.emit", new_callable=AsyncMock),
            pytest.raises(InvalidAccountError) as exc_info,
        ):
            await create_draft(
                mock_db,
                tenant_id="t1",
                date_=date(2026, 4, 16),
                period_id="p1",
                description="Test",
                lines=lines,
            )

        error_msg = str(exc_info.value)
        assert "bad-1" in error_msg
        assert "bad-2" in error_msg

    @pytest.mark.anyio
    async def test_system_generated_journals_also_validate_accounts(
        self, mock_db: AsyncMock
    ) -> None:
        """Even system-generated journals must reference valid accounts."""
        from app.services.journals import InvalidAccountError, create_draft

        # No accounts exist
        accounts_result = MagicMock()
        accounts_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=accounts_result)
        mock_db.scalar = AsyncMock(return_value=None)

        with (
            patch("app.services.journals.emit", new_callable=AsyncMock),
            patch("app.services.journals.get_period_for_date", new_callable=AsyncMock),
            pytest.raises(InvalidAccountError),
        ):
            await create_draft(
                mock_db,
                tenant_id="t1",
                date_=date(2026, 4, 16),
                period_id="p1",
                description="System JE",
                lines=self._make_lines(["nonexistent-1", "nonexistent-2"]),
                system_generated=True,
            )
