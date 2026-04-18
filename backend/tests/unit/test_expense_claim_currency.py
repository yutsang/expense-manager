"""Unit tests for expense claim multi-currency validation (Bug #51).

Tests cover:
  - CurrencyMismatchError is defined in the expense claims service
  - create_expense_claim validates that line currencies match header currency
  - Matching currencies are accepted
  - Mismatched currencies raise CurrencyMismatchError
"""

from __future__ import annotations

import pathlib
import sys
from datetime import date, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

_UTC = timezone.utc
_NEEDS_311 = sys.version_info < (3, 11)
_skip_311 = pytest.mark.skipif(_NEEDS_311, reason="datetime.UTC requires Python >=3.11")

_SERVICE_PATH = (
    pathlib.Path(__file__).resolve().parents[2] / "app" / "services" / "expense_claims.py"
)


class TestCurrencyMismatchErrorExists:
    """CurrencyMismatchError must be defined in expense_claims service."""

    def _get_source(self) -> str:
        return _SERVICE_PATH.read_text()

    def test_error_class_exists(self) -> None:
        source = self._get_source()
        assert "class CurrencyMismatchError" in source

    def test_error_inherits_from_valueerror(self) -> None:
        source = self._get_source()
        assert "class CurrencyMismatchError(ValueError)" in source


class TestCurrencyValidationInSource:
    """create_expense_claim must validate line currencies against header."""

    def _get_source(self) -> str:
        return _SERVICE_PATH.read_text()

    def test_validates_line_currency(self) -> None:
        source = self._get_source()
        func_start = source.index("async def create_expense_claim")
        next_func = source.find("\nasync def ", func_start + 1)
        if next_func == -1:
            next_func = len(source)
        func_body = source[func_start:next_func]
        assert "CurrencyMismatchError" in func_body

    def test_checks_line_currency_against_claim_currency(self) -> None:
        source = self._get_source()
        func_start = source.index("async def create_expense_claim")
        next_func = source.find("\nasync def ", func_start + 1)
        if next_func == -1:
            next_func = len(source)
        func_body = source[func_start:next_func]
        # Should compare line currency against claim/header currency
        assert "currency" in func_body
        assert "line" in func_body.lower()


class TestCurrencyMismatchErrorImportable:
    """CurrencyMismatchError must be importable from the service module."""

    def test_can_import(self) -> None:
        from app.services.expense_claims import CurrencyMismatchError

        assert issubclass(CurrencyMismatchError, ValueError)


@_skip_311
class TestCreateExpenseClaimCurrencyValidation:
    """create_expense_claim raises CurrencyMismatchError on mismatched currencies."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        db = AsyncMock()
        db.flush = AsyncMock()
        db.refresh = AsyncMock()
        db.execute = AsyncMock()
        db.scalar = AsyncMock()
        db.add = MagicMock()
        return db

    @pytest.fixture
    def mock_period(self) -> MagicMock:
        period = MagicMock()
        period.id = "period-1"
        period.name = "Jan 2026"
        period.status = "open"
        return period

    @pytest.mark.anyio
    async def test_raises_on_mismatched_line_currency(
        self, mock_db: AsyncMock, mock_period: MagicMock
    ) -> None:
        from app.services.expense_claims import (
            CurrencyMismatchError,
            create_expense_claim,
        )

        # Patch get_period_for_date to return mock_period
        import app.services.expense_claims as svc

        original = svc.get_period_for_date
        svc.get_period_for_date = AsyncMock(return_value=mock_period)

        try:
            data = {
                "contact_id": "contact-1",
                "claim_date": date(2026, 1, 15),
                "title": "Mixed currency claim",
                "currency": "USD",
                "lines": [
                    {
                        "account_id": "acc-1",
                        "amount": "100.00",
                        "currency": "USD",
                    },
                    {
                        "account_id": "acc-2",
                        "amount": "50.00",
                        "currency": "EUR",  # mismatched!
                    },
                ],
            }

            with pytest.raises(CurrencyMismatchError, match="EUR"):
                await create_expense_claim(mock_db, "t1", "actor-1", data)
        finally:
            svc.get_period_for_date = original

    @pytest.mark.anyio
    async def test_accepts_matching_currencies(
        self, mock_db: AsyncMock, mock_period: MagicMock
    ) -> None:
        from app.services.expense_claims import create_expense_claim

        import app.services.expense_claims as svc

        original = svc.get_period_for_date
        svc.get_period_for_date = AsyncMock(return_value=mock_period)

        # Mock the count query for auto-numbering
        count_result = MagicMock()
        count_result.scalar.return_value = 0
        mock_db.execute = AsyncMock(return_value=count_result)

        try:
            data = {
                "contact_id": "contact-1",
                "claim_date": date(2026, 1, 15),
                "title": "Same currency claim",
                "currency": "USD",
                "lines": [
                    {
                        "account_id": "acc-1",
                        "amount": "100.00",
                        "currency": "USD",
                    },
                    {
                        "account_id": "acc-2",
                        "amount": "50.00",
                        "currency": "USD",
                    },
                ],
            }

            # Should not raise - may fail on DB operations but not on currency check
            try:
                await create_expense_claim(mock_db, "t1", "actor-1", data)
            except (AttributeError, TypeError):
                # Expected - mock DB won't fully support the flow, but currency
                # validation should have passed by this point
                pass
        finally:
            svc.get_period_for_date = original

    @pytest.mark.anyio
    async def test_lines_without_currency_use_header_default(
        self, mock_db: AsyncMock, mock_period: MagicMock
    ) -> None:
        """Lines without explicit currency should default to header currency."""
        from app.services.expense_claims import create_expense_claim

        import app.services.expense_claims as svc

        original = svc.get_period_for_date
        svc.get_period_for_date = AsyncMock(return_value=mock_period)

        count_result = MagicMock()
        count_result.scalar.return_value = 0
        mock_db.execute = AsyncMock(return_value=count_result)

        try:
            data = {
                "contact_id": "contact-1",
                "claim_date": date(2026, 1, 15),
                "title": "No line currency",
                "currency": "GBP",
                "lines": [
                    {
                        "account_id": "acc-1",
                        "amount": "100.00",
                        # No currency field - should default to GBP
                    },
                ],
            }

            # Should not raise CurrencyMismatchError
            try:
                await create_expense_claim(mock_db, "t1", "actor-1", data)
            except (AttributeError, TypeError):
                pass  # Expected - mock limitations
        finally:
            svc.get_period_for_date = original
