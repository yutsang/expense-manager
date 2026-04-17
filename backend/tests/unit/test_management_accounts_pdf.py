"""Unit tests for management accounts PDF export (Issue #45).

Tests cover:
  - PDF generation service exists
  - API endpoint exists
  - PDF builder produces valid bytes (integration with fpdf2)
"""

from __future__ import annotations

import pathlib
import sys

import pytest

_NEEDS_311 = sys.version_info < (3, 11)
_skip_311 = pytest.mark.skipif(_NEEDS_311, reason="datetime.UTC requires Python >=3.11")

_SERVICE_PATH = (
    pathlib.Path(__file__).resolve().parents[2] / "app" / "services" / "management_accounts.py"
)
_API_PATH = pathlib.Path(__file__).resolve().parents[2] / "app" / "api" / "v1" / "reports.py"


class TestManagementAccountsServiceSource:
    """Verify service source structure."""

    def test_service_file_exists(self) -> None:
        assert _SERVICE_PATH.exists(), "management_accounts.py service not found"

    def test_build_pdf_function(self) -> None:
        source = _SERVICE_PATH.read_text()
        assert "def build_management_accounts_pdf(" in source

    def test_uses_fpdf(self) -> None:
        source = _SERVICE_PATH.read_text()
        assert "fpdf" in source.lower() or "FPDF" in source


class TestManagementAccountsApiSource:
    """Verify API endpoint exists in reports router."""

    def test_management_accounts_endpoint(self) -> None:
        source = _API_PATH.read_text()
        assert "management-accounts" in source

    def test_returns_pdf_response(self) -> None:
        source = _API_PATH.read_text()
        # Should return a PDF response (either Response or StreamingResponse)
        assert "application/pdf" in source or "Response" in source


@_skip_311
class TestPdfBuilder:
    """Test the pure PDF builder function with sample data."""

    def test_builds_valid_pdf_bytes(self) -> None:
        from app.services.management_accounts import build_management_accounts_pdf

        pl_data = {
            "from_date": "2026-01-01",
            "to_date": "2026-01-31",
            "total_revenue": "10000.00",
            "total_expenses": "7000.00",
            "net_profit": "3000.00",
            "revenue_lines": [
                {"code": "4000", "name": "Sales Revenue", "balance": "10000.00"},
            ],
            "expense_lines": [
                {"code": "5000", "name": "Cost of Goods Sold", "balance": "5000.00"},
                {"code": "5100", "name": "Salaries", "balance": "2000.00"},
            ],
        }

        bs_data = {
            "as_of": "2026-01-31",
            "assets": {
                "total": "50000.00",
                "lines": [
                    {"code": "1000", "name": "Cash at Bank", "balance": "30000.00"},
                    {"code": "1100", "name": "Accounts Receivable", "balance": "20000.00"},
                ],
            },
            "liabilities": {
                "total": "20000.00",
                "lines": [
                    {"code": "2000", "name": "Accounts Payable", "balance": "20000.00"},
                ],
            },
            "equity": {
                "total": "30000.00",
                "lines": [
                    {"code": "3000", "name": "Share Capital", "balance": "30000.00"},
                ],
            },
        }

        cf_data = {
            "from_date": "2026-01-01",
            "to_date": "2026-01-31",
            "operating_activities": [
                {"label": "Net profit", "amount": "3000.00"},
                {"label": "Change in AR", "amount": "-5000.00"},
            ],
            "investing_activities": [
                {"label": "Change in fixed assets", "amount": "-1000.00"},
            ],
            "financing_activities": [
                {"label": "Change in loans", "amount": "0.00"},
            ],
            "net_change": "-3000.00",
            "opening_cash": "33000.00",
            "closing_cash": "30000.00",
        }

        pdf_bytes = build_management_accounts_pdf(
            company_name="Test Company Ltd",
            period_label="January 2026",
            pl_data=pl_data,
            bs_data=bs_data,
            cf_data=cf_data,
        )

        assert isinstance(pdf_bytes, bytes)
        assert len(pdf_bytes) > 100
        # PDF magic bytes
        assert pdf_bytes[:4] == b"%PDF"

    def test_empty_lines_produces_valid_pdf(self) -> None:
        from app.services.management_accounts import build_management_accounts_pdf

        pdf_bytes = build_management_accounts_pdf(
            company_name="Empty Co",
            period_label="Jan 2026",
            pl_data={
                "from_date": "2026-01-01",
                "to_date": "2026-01-31",
                "total_revenue": "0.00",
                "total_expenses": "0.00",
                "net_profit": "0.00",
                "revenue_lines": [],
                "expense_lines": [],
            },
            bs_data={
                "as_of": "2026-01-31",
                "assets": {"total": "0.00", "lines": []},
                "liabilities": {"total": "0.00", "lines": []},
                "equity": {"total": "0.00", "lines": []},
            },
            cf_data={
                "from_date": "2026-01-01",
                "to_date": "2026-01-31",
                "operating_activities": [],
                "investing_activities": [],
                "financing_activities": [],
                "net_change": "0.00",
                "opening_cash": "0.00",
                "closing_cash": "0.00",
            },
        )

        assert isinstance(pdf_bytes, bytes)
        assert pdf_bytes[:4] == b"%PDF"
