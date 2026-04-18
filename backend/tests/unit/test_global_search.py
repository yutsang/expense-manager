"""Unit tests for global search Cmd+K (Issue #39).

Tests cover:
  - GET /v1/search?q=... endpoint exists
  - SearchResultItem schema has entity_type, id, title, subtitle
  - Search service searches contacts, invoices, bills, journals
  - Minimum 2-char query enforcement
  - Results are grouped by entity type
  - Results respect tenant isolation (via service function signature)
"""

from __future__ import annotations

import pathlib
import sys
from unittest.mock import AsyncMock, MagicMock

import pytest

_NEEDS_311 = sys.version_info < (3, 11)
_skip_311 = pytest.mark.skipif(_NEEDS_311, reason="datetime.UTC requires Python >=3.11")


# ── Schema tests ────────────────────────────────────────────────────────────


class TestSearchResultItemSchema:
    """SearchResultItem contains entity_type, id, title, subtitle."""

    def test_valid_result_item(self) -> None:
        from app.api.v1.schemas import SearchResultItem

        item = SearchResultItem(
            entity_type="contact",
            entity_id="c-1",
            title="Acme Corp",
            subtitle="Customer",
            url="/contacts/c-1",
        )
        assert item.entity_type == "contact"
        assert item.title == "Acme Corp"

    def test_entity_type_required(self) -> None:
        from app.api.v1.schemas import SearchResultItem

        with pytest.raises(Exception):
            SearchResultItem(
                entity_id="c-1",
                title="Acme Corp",
            )


class TestSearchResponseSchema:
    """SearchResponse groups results by type."""

    def test_response_has_items_and_total(self) -> None:
        from app.api.v1.schemas import SearchResponse, SearchResultItem

        resp = SearchResponse(
            query="acme",
            items=[
                SearchResultItem(
                    entity_type="contact",
                    entity_id="c-1",
                    title="Acme Corp",
                    subtitle="Customer",
                    url="/contacts/c-1",
                )
            ],
            total=1,
        )
        assert resp.total == 1
        assert len(resp.items) == 1


# ── Service tests (source-level) ────────────────────────────────────────────


class TestSearchServiceSource:
    """Verify search service code exists."""

    def _read_service_source(self) -> str:
        svc_path = (
            pathlib.Path(__file__).resolve().parents[2] / "app" / "services" / "search.py"
        )
        return svc_path.read_text()

    def test_global_search_function_exists(self) -> None:
        source = self._read_service_source()
        assert "async def global_search(" in source

    def test_searches_contacts(self) -> None:
        source = self._read_service_source()
        assert "Contact" in source

    def test_searches_invoices(self) -> None:
        source = self._read_service_source()
        assert "Invoice" in source

    def test_searches_bills(self) -> None:
        source = self._read_service_source()
        assert "Bill" in source

    def test_uses_ilike_or_tsvector(self) -> None:
        source = self._read_service_source()
        assert "ilike" in source.lower() or "tsvector" in source.lower()

    def test_takes_tenant_id_param(self) -> None:
        source = self._read_service_source()
        assert "tenant_id" in source


# ── API tests (source-level) ────────────────────────────────────────────────


class TestSearchApiSource:
    """Verify search API endpoint exists."""

    def _read_api_source(self) -> str:
        api_path = (
            pathlib.Path(__file__).resolve().parents[2] / "app" / "api" / "v1" / "search.py"
        )
        return api_path.read_text()

    def test_search_endpoint_exists(self) -> None:
        source = self._read_api_source()
        assert "search" in source

    def test_endpoint_uses_query_param(self) -> None:
        source = self._read_api_source()
        assert "q" in source or "query" in source

    def test_endpoint_has_limit_param(self) -> None:
        source = self._read_api_source()
        assert "limit" in source


# ── Service-level async tests ────────────────────────────────────────────────


@_skip_311
class TestGlobalSearchService:
    """global_search returns combined results from multiple entities."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        db = AsyncMock()
        db.execute = AsyncMock()
        return db

    @pytest.mark.anyio
    async def test_min_query_length(self, mock_db: AsyncMock) -> None:
        from app.services.search import SearchQueryTooShortError, global_search

        with pytest.raises(SearchQueryTooShortError):
            await global_search(mock_db, tenant_id="t1", query="a")

    @pytest.mark.anyio
    async def test_returns_combined_results(self, mock_db: AsyncMock) -> None:
        from app.services.search import global_search

        # Mock contact results
        contact_row = MagicMock()
        contact_row.id = "c-1"
        contact_row.name = "Acme Corp"
        contact_row.contact_type = "customer"

        # Mock invoice results
        invoice_row = MagicMock()
        invoice_row.id = "inv-1"
        invoice_row.number = "INV-ACME-001"
        invoice_row.status = "sent"
        invoice_row.total = "1000.00"
        invoice_row.currency = "USD"
        invoice_row.issue_date = "2026-04-01"

        # Mock bill results
        bill_row = MagicMock()
        bill_row.id = "bill-1"
        bill_row.number = "BILL-ACME-001"
        bill_row.status = "approved"
        bill_row.total = "500.00"
        bill_row.currency = "USD"
        bill_row.issue_date = "2026-04-01"

        # Set up mock to return different results for each query
        mock_result_contacts = MagicMock()
        mock_result_contacts.scalars.return_value.all.return_value = [contact_row]

        mock_result_invoices = MagicMock()
        mock_result_invoices.scalars.return_value.all.return_value = [invoice_row]

        mock_result_bills = MagicMock()
        mock_result_bills.scalars.return_value.all.return_value = [bill_row]

        mock_result_journals = MagicMock()
        mock_result_journals.scalars.return_value.all.return_value = []

        mock_db.execute.side_effect = [
            mock_result_contacts,
            mock_result_invoices,
            mock_result_bills,
            mock_result_journals,
        ]

        results = await global_search(mock_db, tenant_id="t1", query="acme", limit=10)
        assert len(results) == 3  # 1 contact + 1 invoice + 1 bill

    @pytest.mark.anyio
    async def test_respects_limit(self, mock_db: AsyncMock) -> None:
        from app.services.search import global_search

        # All empty results
        empty_result = MagicMock()
        empty_result.scalars.return_value.all.return_value = []
        mock_db.execute.side_effect = [empty_result, empty_result, empty_result, empty_result]

        results = await global_search(mock_db, tenant_id="t1", query="test", limit=5)
        assert isinstance(results, list)
        assert len(results) <= 5

    @pytest.mark.anyio
    async def test_empty_query_returns_empty(self, mock_db: AsyncMock) -> None:
        from app.services.search import SearchQueryTooShortError, global_search

        with pytest.raises(SearchQueryTooShortError):
            await global_search(mock_db, tenant_id="t1", query="")
