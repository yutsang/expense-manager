"""Unit tests for credit note workflow (Issue #15).

Tests cover:
  - Invoice model has a nullable credit_note_for_id column
  - InvoiceResponse schema includes credit_note_for_id field
  - void_invoice creates a linked credit note with status 'credit_note'
  - Credit note has negated line amounts
  - Credit note posts a reversing journal entry (Cr AR, Dr Revenue)
  - Original invoice status set to 'void' with credit_note_id reference
  - Cannot void a draft invoice via credit note (only authorised/sent/partial)
  - Cannot void an already-void invoice
  - Cannot void a fully paid invoice
  - API endpoint POST /v1/invoices/{id}/void returns updated invoice
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Model source inspection tests (always run, no runtime import needed)
# ---------------------------------------------------------------------------


class TestInvoiceModelCreditNoteColumn:
    """Invoice model must have a nullable credit_note_for_id column."""

    def _read_models_source(self) -> str:
        import pathlib

        models_path = pathlib.Path(__file__).resolve().parents[2] / "app" / "infra" / "models.py"
        return models_path.read_text()

    def test_credit_note_for_id_column_exists(self) -> None:
        source = self._read_models_source()
        assert "credit_note_for_id" in source

    def test_credit_note_for_id_is_nullable(self) -> None:
        source = self._read_models_source()
        idx = source.index("credit_note_for_id")
        block = source[idx : idx + 200]
        assert "nullable=True" in block

    def test_credit_note_for_id_is_uuid_fk(self) -> None:
        source = self._read_models_source()
        idx = source.index("credit_note_for_id")
        block = source[idx : idx + 300]
        assert "invoices.id" in block


class TestInvoiceResponseCreditNoteField:
    """InvoiceResponse schema includes credit_note_for_id."""

    def test_credit_note_for_id_in_response_schema(self) -> None:
        from app.api.v1.schemas import InvoiceResponse

        assert "credit_note_for_id" in InvoiceResponse.model_fields


# ---------------------------------------------------------------------------
# Service source inspection tests
# ---------------------------------------------------------------------------


class TestCreditNoteServiceSource:
    """Verify service code includes credit note logic."""

    def _read_service_source(self) -> str:
        import pathlib

        svc_path = pathlib.Path(__file__).resolve().parents[2] / "app" / "services" / "invoices.py"
        return svc_path.read_text()

    def test_create_credit_note_function_exists(self) -> None:
        source = self._read_service_source()
        assert "async def create_credit_note(" in source

    def test_void_invoice_calls_create_credit_note(self) -> None:
        source = self._read_service_source()
        # The void_invoice function should call create_credit_note for authorised invoices
        assert "create_credit_note" in source

    def test_credit_note_posts_reversing_journal(self) -> None:
        source = self._read_service_source()
        # Should have logic to post a reversing JE
        assert "reversing" in source.lower() or "JE-CN-" in source


class TestApiEndpointCreditNote:
    """Verify API endpoint code supports credit note on void."""

    def _read_api_source(self) -> str:
        import pathlib

        api_path = (
            pathlib.Path(__file__).resolve().parents[2] / "app" / "api" / "v1" / "invoices.py"
        )
        return api_path.read_text()

    def test_void_endpoint_imports_create_credit_note(self) -> None:
        source = self._read_api_source()
        assert "create_credit_note" in source


# ---------------------------------------------------------------------------
# Service-level async tests (require Python 3.11+)
# ---------------------------------------------------------------------------


class TestCreateCreditNote:
    """create_credit_note creates a linked CN and reversing JE."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        db = AsyncMock()
        db.flush = AsyncMock()
        db.refresh = AsyncMock()
        db.execute = AsyncMock()
        db.scalar = AsyncMock()
        db.add = MagicMock()
        return db

    def _make_invoice(
        self,
        *,
        inv_id: str = "inv-1",
        total: str = "1000.0000",
        subtotal: str = "900.0000",
        tax_total: str = "100.0000",
        status: str = "authorised",
        number: str = "INV-00001",
        tenant_id: str = "t1",
        contact_id: str = "contact-1",
        currency: str = "USD",
        fx_rate: str = "1",
        journal_entry_id: str = "je-1",
    ) -> MagicMock:
        inv = MagicMock()
        inv.id = inv_id
        inv.tenant_id = tenant_id
        inv.status = status
        inv.number = number
        inv.total = Decimal(total)
        inv.subtotal = Decimal(subtotal)
        inv.tax_total = Decimal(tax_total)
        inv.amount_due = Decimal(total)
        inv.functional_total = Decimal(total)
        inv.currency = currency
        inv.fx_rate = Decimal(fx_rate)
        inv.contact_id = contact_id
        inv.issue_date = "2026-01-15"
        inv.due_date = "2026-02-15"
        inv.period_name = "2026-01"
        inv.reference = "REF-001"
        inv.notes = None
        inv.version = 2
        inv.updated_by = None
        inv.journal_entry_id = journal_entry_id
        inv.authorised_by = "actor-1"
        inv.voided_at = None
        inv.credit_note_for_id = None
        return inv

    def _make_invoice_line(
        self,
        *,
        line_no: int = 1,
        account_id: str = "acc-revenue",
        line_amount: str = "900.0000",
        tax_amount: str = "100.0000",
        description: str = "Consulting services",
    ) -> MagicMock:
        line = MagicMock()
        line.line_no = line_no
        line.account_id = account_id
        line.item_id = None
        line.tax_code_id = None
        line.description = description
        line.quantity = Decimal("1")
        line.unit_price = Decimal("900.0000")
        line.discount_pct = Decimal("0")
        line.line_amount = Decimal(line_amount)
        line.tax_amount = Decimal(tax_amount)
        return line

    def _make_ar_account(self) -> MagicMock:
        acc = MagicMock()
        acc.id = "acc-ar"
        acc.code = "1100"
        return acc

    @pytest.mark.anyio
    async def test_creates_credit_note_invoice(self, mock_db: AsyncMock) -> None:
        """create_credit_note should create a new Invoice with status 'credit_note'."""
        from app.services.invoices import create_credit_note

        inv = self._make_invoice()
        lines = [self._make_invoice_line()]
        ar_account = self._make_ar_account()

        mock_db.scalar = AsyncMock(side_effect=[ar_account])

        cn, _je = await create_credit_note(mock_db, "t1", inv, lines, "actor-2")

        assert cn.status == "credit_note"

    @pytest.mark.anyio
    async def test_credit_note_has_negative_amounts(self, mock_db: AsyncMock) -> None:
        """Credit note amounts should be negated from the original."""
        from app.services.invoices import create_credit_note

        inv = self._make_invoice(total="1000.0000", subtotal="900.0000", tax_total="100.0000")
        lines = [self._make_invoice_line(line_amount="900.0000", tax_amount="100.0000")]
        ar_account = self._make_ar_account()

        mock_db.scalar = AsyncMock(side_effect=[ar_account])

        cn, _je = await create_credit_note(mock_db, "t1", inv, lines, "actor-2")

        assert cn.total == Decimal("-1000.0000")
        assert cn.subtotal == Decimal("-900.0000")
        assert cn.tax_total == Decimal("-100.0000")
        assert cn.amount_due == Decimal("-1000.0000")

    @pytest.mark.anyio
    async def test_credit_note_links_to_original(self, mock_db: AsyncMock) -> None:
        """Credit note must reference the original invoice via credit_note_for_id."""
        from app.services.invoices import create_credit_note

        inv = self._make_invoice(inv_id="inv-original")
        lines = [self._make_invoice_line()]
        ar_account = self._make_ar_account()

        mock_db.scalar = AsyncMock(side_effect=[ar_account])

        cn, _je = await create_credit_note(mock_db, "t1", inv, lines, "actor-2")

        assert cn.credit_note_for_id == "inv-original"

    @pytest.mark.anyio
    async def test_credit_note_number_has_cn_prefix(self, mock_db: AsyncMock) -> None:
        """Credit note number should be derived from the original invoice number."""
        from app.services.invoices import create_credit_note

        inv = self._make_invoice(number="INV-00001")
        lines = [self._make_invoice_line()]
        ar_account = self._make_ar_account()

        mock_db.scalar = AsyncMock(side_effect=[ar_account])

        cn, _je = await create_credit_note(mock_db, "t1", inv, lines, "actor-2")

        assert cn.number.startswith("CN-")

    @pytest.mark.anyio
    async def test_credit_note_posts_reversing_je(self, mock_db: AsyncMock) -> None:
        """Credit note should post a reversing journal entry."""
        from app.services.invoices import create_credit_note

        inv = self._make_invoice()
        lines = [self._make_invoice_line()]
        ar_account = self._make_ar_account()

        mock_db.scalar = AsyncMock(side_effect=[ar_account])

        _cn, je = await create_credit_note(mock_db, "t1", inv, lines, "actor-2")

        # JE should exist and be posted
        assert je is not None
        assert je.status == "posted"
        assert je.source_type == "credit_note"

    @pytest.mark.anyio
    async def test_reversing_je_has_correct_number(self, mock_db: AsyncMock) -> None:
        """Reversing JE number should reference the credit note."""
        from app.services.invoices import create_credit_note

        inv = self._make_invoice(number="INV-00001")
        lines = [self._make_invoice_line()]
        ar_account = self._make_ar_account()

        mock_db.scalar = AsyncMock(side_effect=[ar_account])

        cn, je = await create_credit_note(mock_db, "t1", inv, lines, "actor-2")

        assert "CN-" in je.number

    @pytest.mark.anyio
    async def test_reversing_je_credits_ar(self, mock_db: AsyncMock) -> None:
        """Reversing JE should credit AR (opposite of original debit)."""
        from app.infra.models import JournalLine
        from app.services.invoices import create_credit_note

        inv = self._make_invoice(total="1000.0000")
        lines = [self._make_invoice_line(line_amount="1000.0000", tax_amount="0")]
        ar_account = self._make_ar_account()

        mock_db.scalar = AsyncMock(side_effect=[ar_account])

        added_objects: list = []

        def capture_add(obj: object) -> None:
            added_objects.append(obj)

        mock_db.add = MagicMock(side_effect=capture_add)

        _cn, _je = await create_credit_note(mock_db, "t1", inv, lines, "actor-2")

        # Find journal lines that were added
        je_lines = [o for o in added_objects if isinstance(o, JournalLine)]

        # The AR line should have credit equal to the invoice total
        ar_lines = [jl for jl in je_lines if jl.account_id == "acc-ar"]
        assert len(ar_lines) == 1
        assert ar_lines[0].credit == Decimal("1000.0000")
        assert ar_lines[0].debit == Decimal("0")

    @pytest.mark.anyio
    async def test_reversing_je_debits_revenue(self, mock_db: AsyncMock) -> None:
        """Reversing JE should debit revenue accounts (opposite of original credit)."""
        from app.infra.models import JournalLine
        from app.services.invoices import create_credit_note

        inv = self._make_invoice(total="1000.0000")
        lines = [
            self._make_invoice_line(
                account_id="acc-revenue",
                line_amount="1000.0000",
                tax_amount="0",
            )
        ]
        ar_account = self._make_ar_account()

        mock_db.scalar = AsyncMock(side_effect=[ar_account])

        added_objects: list = []

        def capture_add(obj: object) -> None:
            added_objects.append(obj)

        mock_db.add = MagicMock(side_effect=capture_add)

        _cn, _je = await create_credit_note(mock_db, "t1", inv, lines, "actor-2")

        je_lines = [o for o in added_objects if isinstance(o, JournalLine)]
        rev_lines = [jl for jl in je_lines if jl.account_id == "acc-revenue"]
        assert len(rev_lines) == 1
        assert rev_lines[0].debit == Decimal("1000.0000")
        assert rev_lines[0].credit == Decimal("0")

    @pytest.mark.anyio
    async def test_reversing_je_balances(self, mock_db: AsyncMock) -> None:
        """Total debits must equal total credits in the reversing JE."""
        from app.infra.models import JournalLine
        from app.services.invoices import create_credit_note

        inv = self._make_invoice(total="1000.0000", subtotal="900.0000", tax_total="100.0000")
        lines = [self._make_invoice_line(line_amount="900.0000", tax_amount="100.0000")]
        ar_account = self._make_ar_account()

        mock_db.scalar = AsyncMock(side_effect=[ar_account])

        added_objects: list = []

        def capture_add(obj: object) -> None:
            added_objects.append(obj)

        mock_db.add = MagicMock(side_effect=capture_add)

        _cn, _je = await create_credit_note(mock_db, "t1", inv, lines, "actor-2")

        je_lines = [o for o in added_objects if isinstance(o, JournalLine)]
        total_debit = sum(Decimal(str(jl.debit)) for jl in je_lines)
        total_credit = sum(Decimal(str(jl.credit)) for jl in je_lines)
        assert total_debit == total_credit


class TestVoidInvoiceWithCreditNote:
    """void_invoice should create a credit note for authorised invoices."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        db = AsyncMock()
        db.flush = AsyncMock()
        db.refresh = AsyncMock()
        db.scalar = AsyncMock()
        db.add = MagicMock()
        # void_invoice calls db.execute for PaymentAllocation check
        alloc_result = MagicMock()
        alloc_result.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(return_value=alloc_result)
        return db

    def _make_invoice(
        self,
        *,
        status: str = "authorised",
        journal_entry_id: str | None = "je-1",
    ) -> MagicMock:
        inv = MagicMock()
        inv.id = "inv-1"
        inv.tenant_id = "t1"
        inv.status = status
        inv.number = "INV-00001"
        inv.total = Decimal("1000.0000")
        inv.subtotal = Decimal("900.0000")
        inv.tax_total = Decimal("100.0000")
        inv.amount_due = Decimal("1000.0000")
        inv.functional_total = Decimal("1000.0000")
        inv.currency = "USD"
        inv.fx_rate = Decimal("1")
        inv.contact_id = "contact-1"
        inv.issue_date = "2026-01-15"
        inv.due_date = "2026-02-15"
        inv.period_name = "2026-01"
        inv.reference = None
        inv.notes = None
        inv.version = 2
        inv.updated_by = None
        inv.journal_entry_id = journal_entry_id
        inv.authorised_by = "actor-1"
        inv.voided_at = None
        inv.credit_note_for_id = None
        return inv

    @pytest.mark.anyio
    async def test_void_authorised_invoice_sets_status_void(self, mock_db: AsyncMock) -> None:
        """Voiding an authorised invoice should set its status to 'void'."""
        from app.services.invoices import void_invoice

        inv = self._make_invoice(status="authorised")
        cn_mock = MagicMock()
        cn_mock.id = "cn-1"
        je_mock = MagicMock()

        with (
            patch("app.services.invoices.get_invoice", return_value=inv),
            patch("app.services.invoices.get_invoice_lines", return_value=[]),
            patch(
                "app.services.invoices.create_credit_note",
                return_value=(cn_mock, je_mock),
            ),
        ):
            result = await void_invoice(mock_db, "t1", "inv-1", "actor-2")

        assert result.status == "void"

    @pytest.mark.anyio
    async def test_void_authorised_invoice_creates_credit_note(self, mock_db: AsyncMock) -> None:
        """Voiding an authorised invoice should call create_credit_note."""
        from app.services.invoices import void_invoice

        inv = self._make_invoice(status="authorised")
        cn_mock = MagicMock()
        cn_mock.id = "cn-1"
        je_mock = MagicMock()

        with (
            patch("app.services.invoices.get_invoice", return_value=inv),
            patch("app.services.invoices.get_invoice_lines", return_value=[]),
            patch(
                "app.services.invoices.create_credit_note",
                return_value=(cn_mock, je_mock),
            ) as mock_cn,
        ):
            await void_invoice(mock_db, "t1", "inv-1", "actor-2")

        mock_cn.assert_called_once()

    @pytest.mark.anyio
    async def test_void_draft_invoice_no_credit_note(self, mock_db: AsyncMock) -> None:
        """Voiding a draft invoice should NOT create a credit note (no JE was posted)."""
        from app.services.invoices import void_invoice

        inv = self._make_invoice(status="draft", journal_entry_id=None)

        with (
            patch("app.services.invoices.get_invoice", return_value=inv),
            patch(
                "app.services.invoices.create_credit_note",
                return_value=(MagicMock(), MagicMock()),
            ) as mock_cn,
        ):
            result = await void_invoice(mock_db, "t1", "inv-1", "actor-2")

        mock_cn.assert_not_called()
        assert result.status == "void"

    @pytest.mark.anyio
    async def test_void_already_void_raises(self, mock_db: AsyncMock) -> None:
        """Cannot void an already void invoice."""
        from app.services.invoices import InvoiceTransitionError, void_invoice

        inv = self._make_invoice(status="void")

        with (
            patch("app.services.invoices.get_invoice", return_value=inv),
            pytest.raises(InvoiceTransitionError, match="already void"),
        ):
            await void_invoice(mock_db, "t1", "inv-1", "actor-2")

    @pytest.mark.anyio
    async def test_void_paid_invoice_raises(self, mock_db: AsyncMock) -> None:
        """Cannot void a fully paid invoice."""
        from app.services.invoices import InvoiceTransitionError, void_invoice

        inv = self._make_invoice(status="paid")

        with (
            patch("app.services.invoices.get_invoice", return_value=inv),
            pytest.raises(InvoiceTransitionError, match="credit note"),
        ):
            await void_invoice(mock_db, "t1", "inv-1", "actor-2")

    @pytest.mark.anyio
    async def test_void_sent_invoice_creates_credit_note(self, mock_db: AsyncMock) -> None:
        """Voiding a sent invoice (which has a JE) should create a credit note."""
        from app.services.invoices import void_invoice

        inv = self._make_invoice(status="sent", journal_entry_id="je-1")
        cn_mock = MagicMock()
        cn_mock.id = "cn-1"
        je_mock = MagicMock()

        with (
            patch("app.services.invoices.get_invoice", return_value=inv),
            patch("app.services.invoices.get_invoice_lines", return_value=[]),
            patch(
                "app.services.invoices.create_credit_note",
                return_value=(cn_mock, je_mock),
            ) as mock_cn,
        ):
            result = await void_invoice(mock_db, "t1", "inv-1", "actor-2")

        mock_cn.assert_called_once()
        assert result.status == "void"

    @pytest.mark.anyio
    async def test_void_partial_invoice_creates_credit_note(self, mock_db: AsyncMock) -> None:
        """Voiding a partial-paid invoice (which has a JE) should create a credit note."""
        from app.services.invoices import void_invoice

        inv = self._make_invoice(status="partial", journal_entry_id="je-1")
        cn_mock = MagicMock()
        cn_mock.id = "cn-1"
        je_mock = MagicMock()

        with (
            patch("app.services.invoices.get_invoice", return_value=inv),
            patch("app.services.invoices.get_invoice_lines", return_value=[]),
            patch(
                "app.services.invoices.create_credit_note",
                return_value=(cn_mock, je_mock),
            ) as mock_cn,
        ):
            result = await void_invoice(mock_db, "t1", "inv-1", "actor-2")

        mock_cn.assert_called_once()
        assert result.status == "void"


# ---------------------------------------------------------------------------
# Migration source inspection
# ---------------------------------------------------------------------------


class TestCreditNoteMigration:
    """Migration should add credit_note_for_id column."""

    def test_migration_file_exists(self) -> None:
        import pathlib

        migrations_dir = pathlib.Path(__file__).resolve().parents[2] / "migrations" / "versions"
        migration_files = list(migrations_dir.glob("*credit_note*"))
        assert len(migration_files) >= 1, "No migration file for credit_note_for_id found"

    def test_migration_adds_credit_note_for_id(self) -> None:
        import pathlib

        migrations_dir = pathlib.Path(__file__).resolve().parents[2] / "migrations" / "versions"
        migration_files = list(migrations_dir.glob("*credit_note*"))
        assert migration_files, "No migration file for credit_note_for_id"
        source = migration_files[0].read_text()
        assert "credit_note_for_id" in source

    def test_migration_has_downgrade(self) -> None:
        import pathlib

        migrations_dir = pathlib.Path(__file__).resolve().parents[2] / "migrations" / "versions"
        migration_files = list(migrations_dir.glob("*credit_note*"))
        assert migration_files, "No migration file for credit_note_for_id"
        source = migration_files[0].read_text()
        assert "def downgrade()" in source
        assert "drop_column" in source
