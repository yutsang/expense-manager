"""Unit tests for configurable approval workflow engine (Issue #61).

Tests cover:
  - ApprovalRule / ApprovalDelegation model existence in models.py
  - ApprovalRuleCreate / ApprovalRuleUpdate schema validation
  - ApprovalDelegationCreate schema validation
  - ApproveRejectRequest schema (comment field)
  - Service: evaluate_rules with various operators and values
  - Service: create/update/delete rules
  - Service: delegation creation and effective approver lookup
  - Integration: invoice authorise_invoice checks configurable rules
  - Integration: bill approve_bill checks configurable rules
  - Integration: approve functions accept comment parameter
"""

from __future__ import annotations

import sys
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.v1.schemas import (
    ApprovalDelegationCreate,
    ApprovalRuleCreate,
    ApprovalRuleUpdate,
    ApproveRejectRequest,
)

_NEEDS_311 = sys.version_info < (3, 11)
_skip_311 = pytest.mark.skipif(_NEEDS_311, reason="datetime.UTC requires Python >=3.11")


# ---------------------------------------------------------------------------
# Schema tests — run on all Python versions
# ---------------------------------------------------------------------------


class TestApprovalRuleCreateSchema:
    """Validation for ApprovalRuleCreate."""

    def test_valid_rule(self) -> None:
        r = ApprovalRuleCreate(
            entity_type="invoice",
            condition_field="total",
            condition_operator="gte",
            condition_value="10000.0000",
            required_role="admin",
            approval_order=1,
        )
        assert r.entity_type == "invoice"
        assert r.condition_value == "10000.0000"

    def test_rejects_invalid_entity_type(self) -> None:
        with pytest.raises(Exception):
            ApprovalRuleCreate(
                entity_type="purchase_order",  # not allowed
                condition_field="total",
                condition_operator="gte",
                condition_value="100",
                required_role="admin",
            )

    def test_rejects_invalid_operator(self) -> None:
        with pytest.raises(Exception):
            ApprovalRuleCreate(
                entity_type="invoice",
                condition_field="total",
                condition_operator="neq",  # not allowed
                condition_value="100",
                required_role="admin",
            )

    def test_rejects_negative_condition_value(self) -> None:
        with pytest.raises(Exception):
            ApprovalRuleCreate(
                entity_type="invoice",
                condition_field="total",
                condition_operator="gte",
                condition_value="-100",
                required_role="admin",
            )

    def test_rejects_invalid_field(self) -> None:
        with pytest.raises(Exception):
            ApprovalRuleCreate(
                entity_type="invoice",
                condition_field="quantity",  # not allowed
                condition_operator="gte",
                condition_value="100",
                required_role="admin",
            )

    def test_accepts_all_entity_types(self) -> None:
        for et in ("invoice", "bill", "journal", "expense_claim"):
            r = ApprovalRuleCreate(
                entity_type=et,
                condition_field="total",
                condition_operator="gte",
                condition_value="100",
                required_role="admin",
            )
            assert r.entity_type == et

    def test_accepts_all_operators(self) -> None:
        for op in ("gte", "lte", "gt", "lt", "eq"):
            r = ApprovalRuleCreate(
                entity_type="invoice",
                condition_field="total",
                condition_operator=op,
                condition_value="100",
                required_role="admin",
            )
            assert r.condition_operator == op

    def test_accepts_zero_condition_value(self) -> None:
        r = ApprovalRuleCreate(
            entity_type="invoice",
            condition_field="total",
            condition_operator="gte",
            condition_value="0",
            required_role="admin",
        )
        assert r.condition_value == "0"

    def test_default_approval_order(self) -> None:
        r = ApprovalRuleCreate(
            entity_type="invoice",
            condition_field="total",
            condition_operator="gte",
            condition_value="100",
            required_role="admin",
        )
        assert r.approval_order == 1


class TestApprovalRuleUpdateSchema:
    """Validation for ApprovalRuleUpdate."""

    def test_all_fields_optional(self) -> None:
        u = ApprovalRuleUpdate()
        assert u.entity_type is None
        assert u.condition_value is None
        assert u.is_active is None

    def test_rejects_negative_condition_value(self) -> None:
        with pytest.raises(Exception):
            ApprovalRuleUpdate(condition_value="-1")

    def test_accepts_none_condition_value(self) -> None:
        u = ApprovalRuleUpdate(condition_value=None)
        assert u.condition_value is None


class TestApprovalDelegationCreateSchema:
    """Validation for ApprovalDelegationCreate."""

    def test_valid_delegation(self) -> None:
        d = ApprovalDelegationCreate(
            delegator_id="user-1",
            delegate_id="user-2",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 31),
        )
        assert d.delegator_id == "user-1"
        assert d.delegate_id == "user-2"

    def test_rejects_end_before_start(self) -> None:
        with pytest.raises(Exception):
            ApprovalDelegationCreate(
                delegator_id="user-1",
                delegate_id="user-2",
                start_date=date(2026, 2, 1),
                end_date=date(2026, 1, 1),
            )

    def test_rejects_self_delegation(self) -> None:
        with pytest.raises(Exception):
            ApprovalDelegationCreate(
                delegator_id="user-1",
                delegate_id="user-1",
                start_date=date(2026, 1, 1),
                end_date=date(2026, 1, 31),
            )


class TestApproveRejectRequestSchema:
    """Validation for ApproveRejectRequest."""

    def test_comment_optional(self) -> None:
        r = ApproveRejectRequest()
        assert r.comment is None

    def test_comment_accepted(self) -> None:
        r = ApproveRejectRequest(comment="Looks good, approved.")
        assert r.comment == "Looks good, approved."

    def test_empty_body_accepted(self) -> None:
        r = ApproveRejectRequest()
        assert r.comment is None


# ---------------------------------------------------------------------------
# Model source verification — run on all Python versions
# ---------------------------------------------------------------------------


class TestModelsSource:
    """Verify model classes exist in models.py via source inspection."""

    def _read_models(self) -> str:
        import pathlib

        models_path = pathlib.Path(__file__).resolve().parents[2] / "app" / "infra" / "models.py"
        return models_path.read_text()

    def test_approval_rule_class_exists(self) -> None:
        source = self._read_models()
        assert "class ApprovalRule(Base):" in source

    def test_approval_delegation_class_exists(self) -> None:
        source = self._read_models()
        assert "class ApprovalDelegation(Base):" in source

    def test_approval_rules_table_name(self) -> None:
        source = self._read_models()
        assert '"approval_rules"' in source

    def test_approval_delegations_table_name(self) -> None:
        source = self._read_models()
        assert '"approval_delegations"' in source

    def test_entity_type_check_constraint(self) -> None:
        source = self._read_models()
        assert "ck_approval_rules_entity_type" in source

    def test_operator_check_constraint(self) -> None:
        source = self._read_models()
        assert "ck_approval_rules_operator" in source

    def test_delegation_date_range_constraint(self) -> None:
        source = self._read_models()
        assert "ck_approval_delegations_date_range" in source

    def test_delegation_no_self_constraint(self) -> None:
        source = self._read_models()
        assert "ck_approval_delegations_no_self" in source


class TestServiceSource:
    """Verify service code structure via source inspection."""

    def _read_service(self) -> str:
        import pathlib

        svc_path = (
            pathlib.Path(__file__).resolve().parents[2] / "app" / "services" / "approval_rules.py"
        )
        return svc_path.read_text()

    def test_list_rules_function(self) -> None:
        assert "async def list_rules(" in self._read_service()

    def test_create_rule_function(self) -> None:
        assert "async def create_rule(" in self._read_service()

    def test_update_rule_function(self) -> None:
        assert "async def update_rule(" in self._read_service()

    def test_delete_rule_function(self) -> None:
        assert "async def delete_rule(" in self._read_service()

    def test_evaluate_rules_function(self) -> None:
        assert "async def evaluate_rules(" in self._read_service()

    def test_create_delegation_function(self) -> None:
        assert "async def create_delegation(" in self._read_service()

    def test_get_effective_approver_function(self) -> None:
        assert "async def get_effective_approver(" in self._read_service()


class TestAPISource:
    """Verify API endpoint code structure via source inspection."""

    def _read_api(self) -> str:
        import pathlib

        api_path = (
            pathlib.Path(__file__).resolve().parents[2] / "app" / "api" / "v1" / "approval_rules.py"
        )
        return api_path.read_text()

    def test_list_endpoint(self) -> None:
        source = self._read_api()
        assert 'prefix="/approval-rules"' in source

    def test_create_endpoint(self) -> None:
        source = self._read_api()
        assert "async def create(" in source

    def test_update_endpoint(self) -> None:
        source = self._read_api()
        assert "async def update(" in source

    def test_deactivate_endpoint(self) -> None:
        source = self._read_api()
        assert "async def deactivate(" in source

    def test_delegation_endpoints(self) -> None:
        source = self._read_api()
        assert "delegations" in source
        assert "async def create_new_delegation(" in source


class TestMigrationSource:
    """Verify migration exists."""

    def test_migration_file_exists(self) -> None:
        import pathlib

        migration_path = (
            pathlib.Path(__file__).resolve().parents[2]
            / "migrations"
            / "versions"
            / "0045_add_approval_rules_tables.py"
        )
        assert migration_path.exists()

    def test_migration_creates_both_tables(self) -> None:
        import pathlib

        migration_path = (
            pathlib.Path(__file__).resolve().parents[2]
            / "migrations"
            / "versions"
            / "0045_add_approval_rules_tables.py"
        )
        source = migration_path.read_text()
        assert '"approval_rules"' in source
        assert '"approval_delegations"' in source

    def test_migration_has_downgrade(self) -> None:
        import pathlib

        migration_path = (
            pathlib.Path(__file__).resolve().parents[2]
            / "migrations"
            / "versions"
            / "0045_add_approval_rules_tables.py"
        )
        source = migration_path.read_text()
        assert "def downgrade()" in source
        assert "drop_table" in source

    def test_migration_enables_rls(self) -> None:
        import pathlib

        migration_path = (
            pathlib.Path(__file__).resolve().parents[2]
            / "migrations"
            / "versions"
            / "0045_add_approval_rules_tables.py"
        )
        source = migration_path.read_text()
        assert "ENABLE ROW LEVEL SECURITY" in source
        assert "tenant_isolation" in source


class TestExistingServicesUpdated:
    """Verify that existing services check configurable rules."""

    def test_invoices_service_calls_evaluate_rules(self) -> None:
        import pathlib

        svc = pathlib.Path(__file__).resolve().parents[2] / "app" / "services" / "invoices.py"
        source = svc.read_text()
        assert "evaluate_rules" in source

    def test_bills_service_calls_evaluate_rules(self) -> None:
        import pathlib

        svc = pathlib.Path(__file__).resolve().parents[2] / "app" / "services" / "bills.py"
        source = svc.read_text()
        assert "evaluate_rules" in source

    def test_invoice_approve_accepts_comment(self) -> None:
        import pathlib

        svc = pathlib.Path(__file__).resolve().parents[2] / "app" / "services" / "invoices.py"
        source = svc.read_text()
        assert "comment: str | None" in source

    def test_bill_approve_accepts_comment(self) -> None:
        import pathlib

        svc = pathlib.Path(__file__).resolve().parents[2] / "app" / "services" / "bills.py"
        source = svc.read_text()
        assert "comment: str | None" in source

    def test_journal_approve_accepts_comment(self) -> None:
        import pathlib

        svc = pathlib.Path(__file__).resolve().parents[2] / "app" / "services" / "journals.py"
        source = svc.read_text()
        assert "comment: str | None" in source

    def test_invoice_api_passes_comment(self) -> None:
        import pathlib

        api = pathlib.Path(__file__).resolve().parents[2] / "app" / "api" / "v1" / "invoices.py"
        source = api.read_text()
        assert "ApproveRejectRequest" in source

    def test_bill_api_passes_comment(self) -> None:
        import pathlib

        api = pathlib.Path(__file__).resolve().parents[2] / "app" / "api" / "v1" / "bills.py"
        source = api.read_text()
        assert "ApproveRejectRequest" in source

    def test_journal_api_passes_comment(self) -> None:
        import pathlib

        api = pathlib.Path(__file__).resolve().parents[2] / "app" / "api" / "v1" / "journals.py"
        source = api.read_text()
        assert "ApproveRejectRequest" in source


# ---------------------------------------------------------------------------
# Service-level async tests (require Python 3.11+)
# ---------------------------------------------------------------------------


def _make_rule(
    *,
    entity_type: str = "invoice",
    condition_field: str = "total",
    condition_operator: str = "gte",
    condition_value: str = "10000",
    required_role: str = "admin",
    approval_order: int = 1,
    is_active: bool = True,
) -> MagicMock:
    rule = MagicMock()
    rule.entity_type = entity_type
    rule.condition_field = condition_field
    rule.condition_operator = condition_operator
    rule.condition_value = Decimal(condition_value)
    rule.required_role = required_role
    rule.approval_order = approval_order
    rule.is_active = is_active
    return rule


@_skip_311
class TestEvaluateRules:
    """evaluate_rules should match rules based on operator and value."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        return AsyncMock()

    @pytest.mark.anyio
    async def test_gte_matches_when_equal(self, mock_db: AsyncMock) -> None:
        from app.services.approval_rules import evaluate_rules

        rule = _make_rule(condition_operator="gte", condition_value="10000")
        with patch("app.services.approval_rules.list_rules", return_value=[rule]):
            result = await evaluate_rules(mock_db, "t1", "invoice", Decimal("10000"))
        assert len(result) == 1

    @pytest.mark.anyio
    async def test_gte_matches_when_above(self, mock_db: AsyncMock) -> None:
        from app.services.approval_rules import evaluate_rules

        rule = _make_rule(condition_operator="gte", condition_value="10000")
        with patch("app.services.approval_rules.list_rules", return_value=[rule]):
            result = await evaluate_rules(mock_db, "t1", "invoice", Decimal("15000"))
        assert len(result) == 1

    @pytest.mark.anyio
    async def test_gte_no_match_when_below(self, mock_db: AsyncMock) -> None:
        from app.services.approval_rules import evaluate_rules

        rule = _make_rule(condition_operator="gte", condition_value="10000")
        with patch("app.services.approval_rules.list_rules", return_value=[rule]):
            result = await evaluate_rules(mock_db, "t1", "invoice", Decimal("5000"))
        assert len(result) == 0

    @pytest.mark.anyio
    async def test_gt_no_match_when_equal(self, mock_db: AsyncMock) -> None:
        from app.services.approval_rules import evaluate_rules

        rule = _make_rule(condition_operator="gt", condition_value="10000")
        with patch("app.services.approval_rules.list_rules", return_value=[rule]):
            result = await evaluate_rules(mock_db, "t1", "invoice", Decimal("10000"))
        assert len(result) == 0

    @pytest.mark.anyio
    async def test_lt_matches_when_below(self, mock_db: AsyncMock) -> None:
        from app.services.approval_rules import evaluate_rules

        rule = _make_rule(condition_operator="lt", condition_value="10000")
        with patch("app.services.approval_rules.list_rules", return_value=[rule]):
            result = await evaluate_rules(mock_db, "t1", "invoice", Decimal("5000"))
        assert len(result) == 1

    @pytest.mark.anyio
    async def test_lte_matches_when_equal(self, mock_db: AsyncMock) -> None:
        from app.services.approval_rules import evaluate_rules

        rule = _make_rule(condition_operator="lte", condition_value="10000")
        with patch("app.services.approval_rules.list_rules", return_value=[rule]):
            result = await evaluate_rules(mock_db, "t1", "invoice", Decimal("10000"))
        assert len(result) == 1

    @pytest.mark.anyio
    async def test_eq_matches_exact(self, mock_db: AsyncMock) -> None:
        from app.services.approval_rules import evaluate_rules

        rule = _make_rule(condition_operator="eq", condition_value="10000")
        with patch("app.services.approval_rules.list_rules", return_value=[rule]):
            result = await evaluate_rules(mock_db, "t1", "invoice", Decimal("10000"))
        assert len(result) == 1

    @pytest.mark.anyio
    async def test_eq_no_match_when_different(self, mock_db: AsyncMock) -> None:
        from app.services.approval_rules import evaluate_rules

        rule = _make_rule(condition_operator="eq", condition_value="10000")
        with patch("app.services.approval_rules.list_rules", return_value=[rule]):
            result = await evaluate_rules(mock_db, "t1", "invoice", Decimal("10001"))
        assert len(result) == 0

    @pytest.mark.anyio
    async def test_no_rules_returns_empty(self, mock_db: AsyncMock) -> None:
        from app.services.approval_rules import evaluate_rules

        with patch("app.services.approval_rules.list_rules", return_value=[]):
            result = await evaluate_rules(mock_db, "t1", "invoice", Decimal("10000"))
        assert len(result) == 0

    @pytest.mark.anyio
    async def test_multiple_rules_sorted_by_order(self, mock_db: AsyncMock) -> None:
        from app.services.approval_rules import evaluate_rules

        rule1 = _make_rule(
            condition_operator="gte",
            condition_value="5000",
            required_role="accountant",
            approval_order=2,
        )
        rule2 = _make_rule(
            condition_operator="gte",
            condition_value="10000",
            required_role="admin",
            approval_order=1,
        )
        with patch("app.services.approval_rules.list_rules", return_value=[rule1, rule2]):
            result = await evaluate_rules(mock_db, "t1", "invoice", Decimal("15000"))
        assert len(result) == 2
        assert result[0].required_role == "admin"
        assert result[1].required_role == "accountant"


@_skip_311
class TestGetEffectiveApprover:
    """get_effective_approver should check delegations."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        db = AsyncMock()
        db.scalar = AsyncMock()
        return db

    @pytest.mark.anyio
    async def test_no_delegation_returns_original(self, mock_db: AsyncMock) -> None:
        from app.services.approval_rules import get_effective_approver

        mock_db.scalar.return_value = None
        result = await get_effective_approver(mock_db, "t1", "user-1")
        assert result == "user-1"

    @pytest.mark.anyio
    async def test_active_delegation_returns_delegate(self, mock_db: AsyncMock) -> None:
        from app.services.approval_rules import get_effective_approver

        delegation = MagicMock()
        delegation.delegate_id = "user-2"
        mock_db.scalar.return_value = delegation
        result = await get_effective_approver(mock_db, "t1", "user-1")
        assert result == "user-2"


@_skip_311
class TestCreateDelegation:
    """create_delegation validates inputs."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        db = AsyncMock()
        db.add = MagicMock()
        db.flush = AsyncMock()
        db.refresh = AsyncMock()
        return db

    @pytest.mark.anyio
    async def test_rejects_self_delegation(self, mock_db: AsyncMock) -> None:
        from app.services.approval_rules import ApprovalDelegationError, create_delegation

        with pytest.raises(ApprovalDelegationError, match="yourself"):
            await create_delegation(
                mock_db,
                "t1",
                "actor-1",
                delegator_id="user-1",
                delegate_id="user-1",
                start_date=date(2026, 1, 1),
                end_date=date(2026, 1, 31),
            )

    @pytest.mark.anyio
    async def test_rejects_end_before_start(self, mock_db: AsyncMock) -> None:
        from app.services.approval_rules import ApprovalDelegationError, create_delegation

        with pytest.raises(ApprovalDelegationError, match="end_date"):
            await create_delegation(
                mock_db,
                "t1",
                "actor-1",
                delegator_id="user-1",
                delegate_id="user-2",
                start_date=date(2026, 2, 1),
                end_date=date(2026, 1, 1),
            )


@_skip_311
class TestInvoiceRuleIntegration:
    """authorise_invoice should use configurable rules (Issue #61)."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        db = AsyncMock()
        db.flush = AsyncMock()
        db.refresh = AsyncMock()
        db.execute = AsyncMock()
        db.scalar = AsyncMock()
        return db

    def _make_invoice(self, *, total: str = "5000.0000") -> MagicMock:
        inv = MagicMock()
        inv.id = "inv-1"
        inv.tenant_id = "t1"
        inv.status = "draft"
        inv.total = Decimal(total)
        inv.currency = "USD"
        inv.fx_rate = Decimal("1")
        inv.contact_id = "contact-1"
        inv.issue_date = "2026-01-15"
        inv.period_name = "2026-01"
        inv.number = "DRAFT-ABC"
        inv.version = 1
        inv.updated_by = None
        inv.journal_entry_id = None
        return inv

    def _make_tenant(self, *, threshold: str | None = None) -> MagicMock:
        tenant = MagicMock()
        tenant.id = "t1"
        tenant.invoice_approval_threshold = Decimal(threshold) if threshold else None
        return tenant

    @pytest.mark.anyio
    async def test_rule_triggers_awaiting_approval(self, mock_db: AsyncMock) -> None:
        """When a configurable rule matches, invoice should go to awaiting_approval."""
        from app.services.invoices import authorise_invoice

        inv = self._make_invoice(total="15000.0000")
        tenant = self._make_tenant(threshold=None)  # No legacy threshold
        rule = _make_rule(condition_operator="gte", condition_value="10000")

        with (
            patch("app.services.invoices.get_invoice", return_value=inv),
            patch("app.services.invoices.get_invoice_lines", return_value=[]),
            patch("app.services.invoices.get_tenant", return_value=tenant),
            patch("app.services.approval_rules.list_rules", return_value=[rule]),
        ):
            result = await authorise_invoice(mock_db, "t1", "inv-1", "actor-1")

        assert result.status == "awaiting_approval"

    @pytest.mark.anyio
    async def test_no_rules_no_threshold_goes_authorised(self, mock_db: AsyncMock) -> None:
        """With no rules and no legacy threshold, invoice is authorised directly."""
        from app.services.invoices import authorise_invoice

        inv = self._make_invoice(total="15000.0000")
        tenant = self._make_tenant(threshold=None)

        with (
            patch("app.services.invoices.get_invoice", return_value=inv),
            patch("app.services.invoices.get_invoice_lines", return_value=[]),
            patch("app.services.invoices.get_tenant", return_value=tenant),
            patch("app.services.approval_rules.list_rules", return_value=[]),
        ):
            result = await authorise_invoice(mock_db, "t1", "inv-1", "actor-1")

        assert result.status == "authorised"

    @pytest.mark.anyio
    async def test_legacy_threshold_still_works(self, mock_db: AsyncMock) -> None:
        """With no configurable rules, legacy threshold still triggers approval."""
        from app.services.invoices import authorise_invoice

        inv = self._make_invoice(total="15000.0000")
        tenant = self._make_tenant(threshold="10000.0000")

        with (
            patch("app.services.invoices.get_invoice", return_value=inv),
            patch("app.services.invoices.get_invoice_lines", return_value=[]),
            patch("app.services.invoices.get_tenant", return_value=tenant),
            patch("app.services.approval_rules.list_rules", return_value=[]),
        ):
            result = await authorise_invoice(mock_db, "t1", "inv-1", "actor-1")

        assert result.status == "awaiting_approval"
