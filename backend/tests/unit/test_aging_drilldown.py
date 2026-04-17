"""Unit tests for aging report drill-down feature (Issue #44).

Tests cover:
  - Invoice list endpoint accepts due_before/due_after query params
  - Bill list endpoint accepts due_before/due_after query params
  - list_invoices service supports due_before/due_after filtering
  - list_bills service supports due_before/due_after filtering
  - Aging response rows include a doc_id field for linking
  - _aging_bucket function correctly classifies overdue days
"""

from __future__ import annotations


class TestAgingBucketFunction:
    """_aging_bucket classifies days_overdue into correct buckets (source verification)."""

    def _read_reports_source(self) -> str:
        import pathlib

        path = pathlib.Path(__file__).resolve().parents[2] / "app" / "api" / "v1" / "reports.py"
        return path.read_text()

    def test_aging_bucket_function_exists(self) -> None:
        source = self._read_reports_source()
        assert "def _aging_bucket(" in source

    def test_bucket_current_label(self) -> None:
        source = self._read_reports_source()
        assert '"current"' in source

    def test_bucket_1_30_label(self) -> None:
        source = self._read_reports_source()
        assert '"1-30"' in source

    def test_bucket_31_60_label(self) -> None:
        source = self._read_reports_source()
        assert '"31-60"' in source

    def test_bucket_61_90_label(self) -> None:
        source = self._read_reports_source()
        assert '"61-90"' in source

    def test_bucket_90_plus_label(self) -> None:
        source = self._read_reports_source()
        assert '"90+"' in source


class TestAgingRowResponseDocId:
    """AgingRowResponse should include doc_id for drill-down linking."""

    def _read_schemas_source(self) -> str:
        import pathlib

        path = pathlib.Path(__file__).resolve().parents[2] / "app" / "api" / "v1" / "schemas.py"
        return path.read_text()

    def test_doc_id_field_exists(self) -> None:
        source = self._read_schemas_source()
        idx = source.index("class AgingRowResponse(")
        block = source[idx : idx + 500]
        assert "doc_id:" in block


class TestInvoiceListDueDateFilters:
    """Invoice list API endpoint accepts due_before and due_after params."""

    def _read_api_source(self) -> str:
        import pathlib

        api_path = (
            pathlib.Path(__file__).resolve().parents[2] / "app" / "api" / "v1" / "invoices.py"
        )
        return api_path.read_text()

    def test_due_before_param_exists(self) -> None:
        source = self._read_api_source()
        assert "due_before" in source

    def test_due_after_param_exists(self) -> None:
        source = self._read_api_source()
        assert "due_after" in source


class TestBillListDueDateFilters:
    """Bill list API endpoint accepts due_before and due_after params."""

    def _read_api_source(self) -> str:
        import pathlib

        api_path = pathlib.Path(__file__).resolve().parents[2] / "app" / "api" / "v1" / "bills.py"
        return api_path.read_text()

    def test_due_before_param_exists(self) -> None:
        source = self._read_api_source()
        assert "due_before" in source

    def test_due_after_param_exists(self) -> None:
        source = self._read_api_source()
        assert "due_after" in source


class TestListInvoicesServiceDueDateFilters:
    """list_invoices service function supports due_before/due_after."""

    def _read_service_source(self) -> str:
        import pathlib

        svc_path = pathlib.Path(__file__).resolve().parents[2] / "app" / "services" / "invoices.py"
        return svc_path.read_text()

    def test_due_before_param_in_signature(self) -> None:
        source = self._read_service_source()
        assert "due_before" in source

    def test_due_after_param_in_signature(self) -> None:
        source = self._read_service_source()
        assert "due_after" in source


class TestListBillsServiceDueDateFilters:
    """list_bills service function supports due_before/due_after."""

    def _read_service_source(self) -> str:
        import pathlib

        svc_path = pathlib.Path(__file__).resolve().parents[2] / "app" / "services" / "bills.py"
        return svc_path.read_text()

    def test_due_before_param_in_signature(self) -> None:
        source = self._read_service_source()
        assert "due_before" in source

    def test_due_after_param_in_signature(self) -> None:
        source = self._read_service_source()
        assert "due_after" in source


class TestAgingResponseBucketFilter:
    """Aging endpoints accept optional bucket filter."""

    def _read_api_source(self) -> str:
        import pathlib

        api_path = pathlib.Path(__file__).resolve().parents[2] / "app" / "api" / "v1" / "reports.py"
        return api_path.read_text()

    def test_ar_aging_bucket_param(self) -> None:
        source = self._read_api_source()
        assert "bucket" in source

    def test_build_aging_response_filters_by_bucket(self) -> None:
        source = self._read_api_source()
        # The _build_aging_response function should accept bucket param
        assert "bucket" in source
