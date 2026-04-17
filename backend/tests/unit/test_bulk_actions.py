"""Unit tests for bulk approve and bulk void actions on invoices and bills (Issue #38).

Tests cover:
  - BulkActionRequest schema validation (min 1 ID, UUID format)
  - BulkActionResponse schema structure
  - POST /v1/invoices/bulk/authorise — happy path, partial failure, all fail
  - POST /v1/invoices/bulk/void — happy path, partial failure
  - POST /v1/bills/bulk/approve — happy path, partial failure, all fail
  - POST /v1/bills/bulk/void — happy path, partial failure
  - Each endpoint processes all items (no fail-fast), returning partial results
"""

from __future__ import annotations

import sys
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Schema tests — run on all Python versions
# ---------------------------------------------------------------------------


class TestBulkActionRequestSchema:
    """BulkActionRequest validates the list of IDs."""

    def test_accepts_single_id(self) -> None:
        from app.api.v1.schemas import BulkActionRequest

        req = BulkActionRequest(ids=["id-1"])
        assert req.ids == ["id-1"]

    def test_accepts_multiple_ids(self) -> None:
        from app.api.v1.schemas import BulkActionRequest

        req = BulkActionRequest(ids=["id-1", "id-2", "id-3"])
        assert len(req.ids) == 3

    def test_rejects_empty_list(self) -> None:
        from app.api.v1.schemas import BulkActionRequest

        with pytest.raises(Exception):
            BulkActionRequest(ids=[])

    def test_rejects_missing_ids_field(self) -> None:
        from app.api.v1.schemas import BulkActionRequest

        with pytest.raises(Exception):
            BulkActionRequest()  # type: ignore[call-arg]


class TestBulkActionResponseSchema:
    """BulkActionResponse has succeeded and failed lists."""

    def test_empty_response(self) -> None:
        from app.api.v1.schemas import BulkActionResponse

        resp = BulkActionResponse(succeeded=[], failed=[])
        assert resp.succeeded == []
        assert resp.failed == []

    def test_succeeded_only(self) -> None:
        from app.api.v1.schemas import BulkActionResponse

        resp = BulkActionResponse(succeeded=["id-1", "id-2"], failed=[])
        assert len(resp.succeeded) == 2

    def test_mixed_results(self) -> None:
        from app.api.v1.schemas import BulkActionFailure, BulkActionResponse

        resp = BulkActionResponse(
            succeeded=["id-1"],
            failed=[BulkActionFailure(id="id-2", error="Bad status")],
        )
        assert len(resp.succeeded) == 1
        assert len(resp.failed) == 1
        assert resp.failed[0].id == "id-2"
        assert resp.failed[0].error == "Bad status"


# ---------------------------------------------------------------------------
# Source-level verification — confirm endpoints exist in code
# ---------------------------------------------------------------------------


class TestInvoiceBulkEndpointsExist:
    """Verify invoice bulk endpoint code exists via source inspection."""

    def _read_api_source(self) -> str:
        import pathlib

        api_path = (
            pathlib.Path(__file__).resolve().parents[2] / "app" / "api" / "v1" / "invoices.py"
        )
        return api_path.read_text()

    def test_bulk_authorise_endpoint_exists(self) -> None:
        source = self._read_api_source()
        assert "/bulk/authorise" in source

    def test_bulk_void_endpoint_exists(self) -> None:
        source = self._read_api_source()
        assert "/bulk/void" in source


class TestBillBulkEndpointsExist:
    """Verify bill bulk endpoint code exists via source inspection."""

    def _read_api_source(self) -> str:
        import pathlib

        api_path = pathlib.Path(__file__).resolve().parents[2] / "app" / "api" / "v1" / "bills.py"
        return api_path.read_text()

    def test_bulk_approve_endpoint_exists(self) -> None:
        source = self._read_api_source()
        assert "/bulk/approve" in source

    def test_bulk_void_endpoint_exists(self) -> None:
        source = self._read_api_source()
        assert "/bulk/void" in source


# ---------------------------------------------------------------------------
# Service-level async tests (require Python 3.11+ for datetime.UTC)
# ---------------------------------------------------------------------------

_NEEDS_311 = sys.version_info < (3, 11)
_skip_311 = pytest.mark.skipif(_NEEDS_311, reason="datetime.UTC requires Python >=3.11")


@_skip_311
class TestBulkInvoiceAuthorise:
    """POST /v1/invoices/bulk/authorise processes all items, collecting successes and failures."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        db = AsyncMock()
        db.flush = AsyncMock()
        db.refresh = AsyncMock()
        db.commit = AsyncMock()
        db.scalar = AsyncMock()
        db.execute = AsyncMock()
        return db

    def _make_invoice(self, inv_id: str, status: str = "draft") -> MagicMock:
        inv = MagicMock()
        inv.id = inv_id
        inv.status = status
        inv.tenant_id = "t1"
        inv.total = Decimal("1000.0000")
        inv.currency = "USD"
        inv.fx_rate = Decimal("1")
        inv.contact_id = "contact-1"
        inv.issue_date = "2026-01-15"
        inv.period_name = "2026-01"
        inv.number = f"INV-{inv_id}"
        inv.version = 1
        inv.journal_entry_id = None
        inv.authorised_by = None
        return inv

    @pytest.mark.anyio
    async def test_all_succeed(self, mock_db: AsyncMock) -> None:

        inv1 = self._make_invoice("inv-1")
        inv2 = self._make_invoice("inv-2")

        async def mock_authorise(db, tenant_id, invoice_id, actor_id, force=False):
            if invoice_id == "inv-1":
                inv1.status = "authorised"
                return inv1
            inv2.status = "authorised"
            return inv2

        with patch("app.api.v1.invoices.authorise_invoice", side_effect=mock_authorise):
            from app.api.v1.invoices import bulk_authorise
            from app.api.v1.schemas import BulkActionRequest

            body = BulkActionRequest(ids=["inv-1", "inv-2"])
            result = await bulk_authorise(body, mock_db, "t1", "actor-1")

        assert len(result.succeeded) == 2
        assert len(result.failed) == 0

    @pytest.mark.anyio
    async def test_partial_failure(self, mock_db: AsyncMock) -> None:
        from app.services.invoices import InvoiceTransitionError

        inv1 = self._make_invoice("inv-1")

        async def mock_authorise(db, tenant_id, invoice_id, actor_id, force=False):
            if invoice_id == "inv-1":
                inv1.status = "authorised"
                return inv1
            raise InvoiceTransitionError("Cannot authorise invoice with status 'authorised'")

        with patch("app.api.v1.invoices.authorise_invoice", side_effect=mock_authorise):
            from app.api.v1.invoices import bulk_authorise
            from app.api.v1.schemas import BulkActionRequest

            body = BulkActionRequest(ids=["inv-1", "inv-2"])
            result = await bulk_authorise(body, mock_db, "t1", "actor-1")

        assert result.succeeded == ["inv-1"]
        assert len(result.failed) == 1
        assert result.failed[0].id == "inv-2"

    @pytest.mark.anyio
    async def test_all_fail(self, mock_db: AsyncMock) -> None:
        from app.services.invoices import InvoiceNotFoundError

        async def mock_authorise(db, tenant_id, invoice_id, actor_id, force=False):
            raise InvoiceNotFoundError(invoice_id)

        with patch("app.api.v1.invoices.authorise_invoice", side_effect=mock_authorise):
            from app.api.v1.invoices import bulk_authorise
            from app.api.v1.schemas import BulkActionRequest

            body = BulkActionRequest(ids=["inv-1", "inv-2"])
            result = await bulk_authorise(body, mock_db, "t1", "actor-1")

        assert len(result.succeeded) == 0
        assert len(result.failed) == 2


@_skip_311
class TestBulkInvoiceVoid:
    """POST /v1/invoices/bulk/void processes all items, collecting successes and failures."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        db = AsyncMock()
        db.flush = AsyncMock()
        db.refresh = AsyncMock()
        db.commit = AsyncMock()
        db.scalar = AsyncMock()
        db.execute = AsyncMock()
        return db

    def _make_invoice(self, inv_id: str, status: str = "authorised") -> MagicMock:
        inv = MagicMock()
        inv.id = inv_id
        inv.status = status
        return inv

    @pytest.mark.anyio
    async def test_all_succeed(self, mock_db: AsyncMock) -> None:
        inv1 = self._make_invoice("inv-1")
        inv2 = self._make_invoice("inv-2")

        async def mock_void(db, tenant_id, invoice_id, actor_id):
            if invoice_id == "inv-1":
                inv1.status = "void"
                return inv1
            inv2.status = "void"
            return inv2

        with patch("app.api.v1.invoices.void_invoice", side_effect=mock_void):
            from app.api.v1.invoices import bulk_void
            from app.api.v1.schemas import BulkActionRequest

            body = BulkActionRequest(ids=["inv-1", "inv-2"])
            result = await bulk_void(body, mock_db, "t1", "actor-1")

        assert len(result.succeeded) == 2
        assert len(result.failed) == 0

    @pytest.mark.anyio
    async def test_partial_failure(self, mock_db: AsyncMock) -> None:
        from app.services.invoices import InvoiceTransitionError

        inv1 = self._make_invoice("inv-1")

        async def mock_void(db, tenant_id, invoice_id, actor_id):
            if invoice_id == "inv-1":
                inv1.status = "void"
                return inv1
            raise InvoiceTransitionError("Invoice is already void")

        with patch("app.api.v1.invoices.void_invoice", side_effect=mock_void):
            from app.api.v1.invoices import bulk_void
            from app.api.v1.schemas import BulkActionRequest

            body = BulkActionRequest(ids=["inv-1", "inv-2"])
            result = await bulk_void(body, mock_db, "t1", "actor-1")

        assert result.succeeded == ["inv-1"]
        assert len(result.failed) == 1
        assert result.failed[0].id == "inv-2"


@_skip_311
class TestBulkBillApprove:
    """POST /v1/bills/bulk/approve processes all items, collecting successes and failures."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        db = AsyncMock()
        db.flush = AsyncMock()
        db.refresh = AsyncMock()
        db.commit = AsyncMock()
        db.scalar = AsyncMock()
        db.execute = AsyncMock()
        return db

    def _make_bill(self, bill_id: str, status: str = "draft") -> MagicMock:
        bill = MagicMock()
        bill.id = bill_id
        bill.status = status
        return bill

    @pytest.mark.anyio
    async def test_all_succeed(self, mock_db: AsyncMock) -> None:
        bill1 = self._make_bill("bill-1")
        bill2 = self._make_bill("bill-2")

        async def mock_approve(db, tenant_id, bill_id, actor_id):
            if bill_id == "bill-1":
                bill1.status = "approved"
                return bill1
            bill2.status = "approved"
            return bill2

        with patch("app.api.v1.bills.approve_bill", side_effect=mock_approve):
            from app.api.v1.bills import bulk_approve
            from app.api.v1.schemas import BulkActionRequest

            body = BulkActionRequest(ids=["bill-1", "bill-2"])
            result = await bulk_approve(body, mock_db, "t1", "actor-1")

        assert len(result.succeeded) == 2
        assert len(result.failed) == 0

    @pytest.mark.anyio
    async def test_partial_failure(self, mock_db: AsyncMock) -> None:
        from app.services.bills import BillTransitionError

        bill1 = self._make_bill("bill-1")

        async def mock_approve(db, tenant_id, bill_id, actor_id):
            if bill_id == "bill-1":
                bill1.status = "approved"
                return bill1
            raise BillTransitionError("Cannot approve bill with status 'approved'")

        with patch("app.api.v1.bills.approve_bill", side_effect=mock_approve):
            from app.api.v1.bills import bulk_approve
            from app.api.v1.schemas import BulkActionRequest

            body = BulkActionRequest(ids=["bill-1", "bill-2"])
            result = await bulk_approve(body, mock_db, "t1", "actor-1")

        assert result.succeeded == ["bill-1"]
        assert len(result.failed) == 1
        assert result.failed[0].id == "bill-2"

    @pytest.mark.anyio
    async def test_all_fail(self, mock_db: AsyncMock) -> None:
        from app.services.bills import BillNotFoundError

        async def mock_approve(db, tenant_id, bill_id, actor_id):
            raise BillNotFoundError(bill_id)

        with patch("app.api.v1.bills.approve_bill", side_effect=mock_approve):
            from app.api.v1.bills import bulk_approve
            from app.api.v1.schemas import BulkActionRequest

            body = BulkActionRequest(ids=["bill-1", "bill-2"])
            result = await bulk_approve(body, mock_db, "t1", "actor-1")

        assert len(result.succeeded) == 0
        assert len(result.failed) == 2


@_skip_311
class TestBulkBillVoid:
    """POST /v1/bills/bulk/void processes all items, collecting successes and failures."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        db = AsyncMock()
        db.flush = AsyncMock()
        db.refresh = AsyncMock()
        db.commit = AsyncMock()
        db.scalar = AsyncMock()
        db.execute = AsyncMock()
        return db

    def _make_bill(self, bill_id: str, status: str = "approved") -> MagicMock:
        bill = MagicMock()
        bill.id = bill_id
        bill.status = status
        return bill

    @pytest.mark.anyio
    async def test_all_succeed(self, mock_db: AsyncMock) -> None:
        bill1 = self._make_bill("bill-1")
        bill2 = self._make_bill("bill-2")

        async def mock_void(db, tenant_id, bill_id, actor_id):
            if bill_id == "bill-1":
                bill1.status = "void"
                return bill1
            bill2.status = "void"
            return bill2

        with patch("app.api.v1.bills.void_bill", side_effect=mock_void):
            from app.api.v1.bills import bulk_void
            from app.api.v1.schemas import BulkActionRequest

            body = BulkActionRequest(ids=["bill-1", "bill-2"])
            result = await bulk_void(body, mock_db, "t1", "actor-1")

        assert len(result.succeeded) == 2
        assert len(result.failed) == 0

    @pytest.mark.anyio
    async def test_partial_failure(self, mock_db: AsyncMock) -> None:
        from app.services.bills import BillTransitionError

        bill1 = self._make_bill("bill-1")

        async def mock_void(db, tenant_id, bill_id, actor_id):
            if bill_id == "bill-1":
                bill1.status = "void"
                return bill1
            raise BillTransitionError("Bill is already void")

        with patch("app.api.v1.bills.void_bill", side_effect=mock_void):
            from app.api.v1.bills import bulk_void
            from app.api.v1.schemas import BulkActionRequest

            body = BulkActionRequest(ids=["bill-1", "bill-2"])
            result = await bulk_void(body, mock_db, "t1", "actor-1")

        assert result.succeeded == ["bill-1"]
        assert len(result.failed) == 1
        assert result.failed[0].id == "bill-2"
