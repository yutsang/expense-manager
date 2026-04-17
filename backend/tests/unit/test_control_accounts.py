"""Unit tests for control-account guard (Issue #18).

Tests cover:
  - AccountResponse schema includes is_control_account field
  - AccountCreate schema includes is_control_account field
  - create_draft() rejects lines referencing control accounts
  - create_draft() allows control accounts when system_generated=True
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.v1.schemas import AccountCreate, AccountResponse
from app.domain.ledger.journal import JournalLineInput
from app.services.journals import ControlAccountError, create_draft

# ── Schema tests ─────────────────────────────────────────────────────────────


class TestAccountResponseControlField:
    def test_includes_is_control_account_defaults_false(self) -> None:
        resp = AccountResponse(
            id="acc-1",
            code="1000",
            name="Cash",
            type="asset",
            subtype="current_asset",
            normal_balance="debit",
            parent_id=None,
            is_active=True,
            is_system=False,
            is_control_account=False,
            currency=None,
            description=None,
            created_at=datetime(2025, 1, 1),
            updated_at=datetime(2025, 1, 1),
        )
        assert resp.is_control_account is False

    def test_is_control_account_true(self) -> None:
        resp = AccountResponse(
            id="acc-1",
            code="1100",
            name="Accounts Receivable",
            type="asset",
            subtype="current_asset",
            normal_balance="debit",
            parent_id=None,
            is_active=True,
            is_system=True,
            is_control_account=True,
            currency=None,
            description=None,
            created_at=datetime(2025, 1, 1),
            updated_at=datetime(2025, 1, 1),
        )
        assert resp.is_control_account is True


class TestAccountCreateControlField:
    def test_defaults_to_false(self) -> None:
        a = AccountCreate(
            code="1000",
            name="Cash",
            type="asset",
            normal_balance="debit",
        )
        assert a.is_control_account is False

    def test_can_be_set_to_true(self) -> None:
        a = AccountCreate(
            code="1100",
            name="Accounts Receivable",
            type="asset",
            normal_balance="debit",
            is_control_account=True,
        )
        assert a.is_control_account is True


# ── Service guard tests ──────────────────────────────────────────────────────


def _make_account(account_id: str, is_control: bool) -> MagicMock:
    """Create a mock Account ORM object."""
    acct = MagicMock()
    acct.id = account_id
    acct.is_control_account = is_control
    return acct


def _make_lines(account_ids: list[str]) -> list[JournalLineInput]:
    """Build balanced journal lines; first line is debit, second is credit."""
    assert len(account_ids) == 2, "helper expects exactly 2 account_ids"
    return [
        JournalLineInput(
            account_id=account_ids[0],
            debit=Decimal("100"),
            credit=Decimal("0"),
            currency="USD",
            functional_debit=Decimal("100"),
            functional_credit=Decimal("0"),
        ),
        JournalLineInput(
            account_id=account_ids[1],
            debit=Decimal("0"),
            credit=Decimal("100"),
            currency="USD",
            functional_debit=Decimal("0"),
            functional_credit=Decimal("100"),
        ),
    ]


@pytest.mark.asyncio
class TestControlAccountGuard:
    """Tests for the control-account guard in create_draft()."""

    async def test_rejects_control_account_in_manual_entry(self) -> None:
        """POST /v1/journals should return 422 if any line references a control account."""
        db = AsyncMock()

        # Mock the account lookup to return one control account
        ar_account = _make_account("acc-ar", is_control=True)
        cash_account = _make_account("acc-cash", is_control=False)

        # scalars().all() returns the list of accounts
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [ar_account, cash_account]
        db.execute.return_value = mock_result
        db.flush = AsyncMock()

        lines = _make_lines(["acc-ar", "acc-cash"])

        with pytest.raises(ControlAccountError, match="control account"):
            await create_draft(
                db,
                tenant_id="t-1",
                date_=date(2025, 1, 15),
                period_id="p-1",
                description="Test manual entry",
                lines=lines,
                source_type="manual",
                actor_id="user-1",
            )

    async def test_allows_system_generated_entry_on_control_account(self) -> None:
        """System-generated JEs (from invoice/bill authorization) bypass the guard."""
        db = AsyncMock()

        # Mock the account lookup — both are control accounts
        ar_account = _make_account("acc-ar", is_control=True)
        revenue_account = _make_account("acc-rev", is_control=False)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [ar_account, revenue_account]
        db.execute.return_value = mock_result
        db.flush = AsyncMock()

        lines = _make_lines(["acc-ar", "acc-rev"])

        # Patch emit and _next_number since we don't care about them here
        with (patch("app.services.journals.emit", new_callable=AsyncMock),):
            je = await create_draft(
                db,
                tenant_id="t-1",
                date_=date(2025, 1, 15),
                period_id="p-1",
                description="Invoice authorization JE",
                lines=lines,
                source_type="invoice",
                source_id="inv-1",
                actor_id="user-1",
                system_generated=True,
            )
            assert je is not None

    async def test_allows_non_control_accounts_in_manual_entry(self) -> None:
        """Manual entries targeting normal (non-control) accounts should succeed."""
        db = AsyncMock()

        cash_account = _make_account("acc-cash", is_control=False)
        expense_account = _make_account("acc-exp", is_control=False)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [cash_account, expense_account]
        db.execute.return_value = mock_result
        db.flush = AsyncMock()

        lines = _make_lines(["acc-cash", "acc-exp"])

        with (patch("app.services.journals.emit", new_callable=AsyncMock),):
            je = await create_draft(
                db,
                tenant_id="t-1",
                date_=date(2025, 1, 15),
                period_id="p-1",
                description="Rent payment",
                lines=lines,
                source_type="manual",
                actor_id="user-1",
            )
            assert je is not None

    async def test_error_message_lists_offending_accounts(self) -> None:
        """The error message should identify which account(s) are control accounts."""
        db = AsyncMock()

        ar_account = _make_account("acc-ar", is_control=True)
        ar_account.code = "1100"
        ar_account.name = "Accounts Receivable"
        ap_account = _make_account("acc-ap", is_control=True)
        ap_account.code = "2000"
        ap_account.name = "Accounts Payable"

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [ar_account, ap_account]
        db.execute.return_value = mock_result
        db.flush = AsyncMock()

        lines = _make_lines(["acc-ar", "acc-ap"])

        with pytest.raises(ControlAccountError) as exc_info:
            await create_draft(
                db,
                tenant_id="t-1",
                date_=date(2025, 1, 15),
                period_id="p-1",
                description="Bad entry",
                lines=lines,
                source_type="manual",
                actor_id="user-1",
            )
        msg = str(exc_info.value)
        assert "1100" in msg
        assert "2000" in msg
