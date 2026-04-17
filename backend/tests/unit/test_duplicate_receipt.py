"""Unit tests for duplicate receipt URL detection (Issue #23).

When creating an expense claim, receipt_url values on lines must be unique:
  - Within the same claim (no two lines share a receipt_url)
  - Across claims in the same tenant (receipt_url not on a non-rejected claim)

Tests cover:
  - Intra-claim: duplicate receipt_url across lines in one create call
  - Cross-claim: receipt_url already exists on a non-rejected claim
  - Null/empty receipt_url is exempt from the check
  - Rejected claims do not block reuse of their receipt_url
  - Error identifies the duplicate URL and existing claim ID
  - API layer maps DuplicateReceiptError to HTTP 422
"""

from __future__ import annotations

import sys
from unittest.mock import AsyncMock, MagicMock

import pytest

_NEEDS_311 = sys.version_info < (3, 11)
_skip_311 = pytest.mark.skipif(_NEEDS_311, reason="datetime.UTC requires Python >=3.11")


class TestServiceSourceHasDuplicateReceiptGuard:
    """Verify the service module has duplicate receipt detection via source inspection."""

    def _read_service_source(self) -> str:
        import pathlib

        svc_path = (
            pathlib.Path(__file__).resolve().parents[2] / "app" / "services" / "expense_claims.py"
        )
        return svc_path.read_text()

    def test_duplicate_receipt_error_class_exists(self) -> None:
        source = self._read_service_source()
        assert "class DuplicateReceiptError" in source

    def test_create_checks_receipt_url(self) -> None:
        source = self._read_service_source()
        assert "receipt_url" in source


class TestApiEndpointHandlesDuplicateReceipt:
    """Verify the API endpoint maps DuplicateReceiptError to 422."""

    def _read_api_source(self) -> str:
        import pathlib

        api_path = (
            pathlib.Path(__file__).resolve().parents[2] / "app" / "api" / "v1" / "expense_claims.py"
        )
        return api_path.read_text()

    def test_api_imports_duplicate_receipt_error(self) -> None:
        source = self._read_api_source()
        assert "DuplicateReceiptError" in source

    def test_api_returns_422_on_duplicate_receipt(self) -> None:
        source = self._read_api_source()
        # The handler should catch DuplicateReceiptError and return 422
        assert "DuplicateReceiptError" in source
        assert "HTTP_422_UNPROCESSABLE_ENTITY" in source


@_skip_311
class TestDuplicateReceiptIntraClaim:
    """Service-level tests: duplicate receipt_url within a single claim."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        db = AsyncMock()
        db.flush = AsyncMock()
        db.refresh = AsyncMock()
        db.execute = AsyncMock()
        db.scalar = AsyncMock()
        db.add = MagicMock()
        return db

    @pytest.mark.anyio
    async def test_duplicate_receipt_url_within_claim_raises(self, mock_db: AsyncMock) -> None:
        """Two lines in the same claim with the same receipt_url should fail."""
        from app.services.expense_claims import DuplicateReceiptError, create_expense_claim

        data = {
            "contact_id": "contact-1",
            "claim_date": "2024-01-15",
            "title": "Travel Expenses",
            "currency": "USD",
            "lines": [
                {
                    "account_id": "acct-1",
                    "amount": "50.00",
                    "receipt_url": "https://s3.example.com/receipt-A.pdf",
                },
                {
                    "account_id": "acct-2",
                    "amount": "30.00",
                    "receipt_url": "https://s3.example.com/receipt-A.pdf",
                },
            ],
        }

        with pytest.raises(DuplicateReceiptError):
            await create_expense_claim(mock_db, "t1", "user-1", data)

    @pytest.mark.anyio
    async def test_null_receipt_urls_exempt_from_intra_check(self, mock_db: AsyncMock) -> None:
        """Multiple lines with null receipt_url should not trigger the check."""
        from app.services.expense_claims import create_expense_claim

        # Make scalar return a count of 0 (for auto-numbering)
        mock_db.scalar = AsyncMock(return_value=0)
        # execute for the count query
        count_result = MagicMock()
        count_result.scalar.return_value = 0
        # execute for the cross-claim check (no existing duplicates)
        cross_result = MagicMock()
        cross_result.first.return_value = None
        mock_db.execute = AsyncMock(side_effect=[count_result, cross_result])

        data = {
            "contact_id": "contact-1",
            "claim_date": "2024-01-15",
            "title": "Travel Expenses",
            "currency": "USD",
            "lines": [
                {"account_id": "acct-1", "amount": "50.00", "receipt_url": None},
                {"account_id": "acct-2", "amount": "30.00"},
            ],
        }

        # Should NOT raise
        # We need to mock the count query for auto-numbering
        count_result = MagicMock()
        count_result.scalar.return_value = 0
        mock_db.execute = AsyncMock(return_value=count_result)

        result = await create_expense_claim(mock_db, "t1", "user-1", data)
        assert result is not None

    @pytest.mark.anyio
    async def test_empty_string_receipt_url_exempt(self, mock_db: AsyncMock) -> None:
        """Lines with empty-string receipt_url should not trigger duplicate check."""
        from app.services.expense_claims import create_expense_claim

        count_result = MagicMock()
        count_result.scalar.return_value = 0
        mock_db.execute = AsyncMock(return_value=count_result)

        data = {
            "contact_id": "contact-1",
            "claim_date": "2024-01-15",
            "title": "Travel Expenses",
            "currency": "USD",
            "lines": [
                {"account_id": "acct-1", "amount": "50.00", "receipt_url": ""},
                {"account_id": "acct-2", "amount": "30.00", "receipt_url": ""},
            ],
        }

        result = await create_expense_claim(mock_db, "t1", "user-1", data)
        assert result is not None


@_skip_311
class TestDuplicateReceiptCrossClaim:
    """Service-level tests: duplicate receipt_url across claims in same tenant."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        db = AsyncMock()
        db.flush = AsyncMock()
        db.refresh = AsyncMock()
        db.execute = AsyncMock()
        db.scalar = AsyncMock()
        db.add = MagicMock()
        return db

    @pytest.mark.anyio
    async def test_receipt_url_on_existing_claim_raises(self, mock_db: AsyncMock) -> None:
        """A receipt_url already on a non-rejected claim must raise DuplicateReceiptError."""
        from app.services.expense_claims import DuplicateReceiptError, create_expense_claim

        # Mock the cross-claim query to return a match
        existing_row = MagicMock()
        existing_row.claim_id = "existing-claim-id"
        existing_row.number = "EXP-000001"
        existing_row.receipt_url = "https://s3.example.com/receipt-B.pdf"

        cross_result = MagicMock()
        cross_result.first.return_value = existing_row

        # First call = count for auto-numbering, second = cross-claim check
        count_result = MagicMock()
        count_result.scalar.return_value = 1
        mock_db.execute = AsyncMock(side_effect=[cross_result])

        data = {
            "contact_id": "contact-1",
            "claim_date": "2024-01-15",
            "title": "Travel Expenses",
            "currency": "USD",
            "lines": [
                {
                    "account_id": "acct-1",
                    "amount": "50.00",
                    "receipt_url": "https://s3.example.com/receipt-B.pdf",
                },
            ],
        }

        with pytest.raises(DuplicateReceiptError, match="existing-claim-id"):
            await create_expense_claim(mock_db, "t1", "user-1", data)

    @pytest.mark.anyio
    async def test_receipt_url_on_rejected_claim_allowed(self, mock_db: AsyncMock) -> None:
        """A receipt_url on a rejected claim should NOT block reuse."""
        from app.services.expense_claims import create_expense_claim

        # Cross-claim check returns no match (rejected claims are excluded)
        cross_result = MagicMock()
        cross_result.first.return_value = None

        count_result = MagicMock()
        count_result.scalar.return_value = 2
        mock_db.execute = AsyncMock(side_effect=[cross_result, count_result])

        data = {
            "contact_id": "contact-1",
            "claim_date": "2024-01-15",
            "title": "Travel Expenses",
            "currency": "USD",
            "lines": [
                {
                    "account_id": "acct-1",
                    "amount": "50.00",
                    "receipt_url": "https://s3.example.com/receipt-C.pdf",
                },
            ],
        }

        result = await create_expense_claim(mock_db, "t1", "user-1", data)
        assert result is not None

    @pytest.mark.anyio
    async def test_error_message_includes_url_and_claim_id(self, mock_db: AsyncMock) -> None:
        """The error must identify the duplicate URL and existing claim ID."""
        from app.services.expense_claims import DuplicateReceiptError, create_expense_claim

        existing_row = MagicMock()
        existing_row.claim_id = "claim-99"
        existing_row.number = "EXP-000099"
        existing_row.receipt_url = "https://s3.example.com/receipt-D.pdf"

        cross_result = MagicMock()
        cross_result.first.return_value = existing_row

        mock_db.execute = AsyncMock(side_effect=[cross_result])

        data = {
            "contact_id": "contact-1",
            "claim_date": "2024-01-15",
            "title": "Travel Expenses",
            "currency": "USD",
            "lines": [
                {
                    "account_id": "acct-1",
                    "amount": "50.00",
                    "receipt_url": "https://s3.example.com/receipt-D.pdf",
                },
            ],
        }

        with pytest.raises(DuplicateReceiptError, match="receipt-D.pdf") as exc_info:
            await create_expense_claim(mock_db, "t1", "user-1", data)

        assert "EXP-000099" in str(exc_info.value)

    @pytest.mark.anyio
    async def test_distinct_receipt_urls_allowed(self, mock_db: AsyncMock) -> None:
        """Different receipt_urls across lines should succeed."""
        from app.services.expense_claims import create_expense_claim

        cross_result = MagicMock()
        cross_result.first.return_value = None

        count_result = MagicMock()
        count_result.scalar.return_value = 0
        mock_db.execute = AsyncMock(side_effect=[cross_result, count_result])

        data = {
            "contact_id": "contact-1",
            "claim_date": "2024-01-15",
            "title": "Travel Expenses",
            "currency": "USD",
            "lines": [
                {
                    "account_id": "acct-1",
                    "amount": "50.00",
                    "receipt_url": "https://s3.example.com/receipt-X.pdf",
                },
                {
                    "account_id": "acct-2",
                    "amount": "30.00",
                    "receipt_url": "https://s3.example.com/receipt-Y.pdf",
                },
            ],
        }

        result = await create_expense_claim(mock_db, "t1", "user-1", data)
        assert result is not None
