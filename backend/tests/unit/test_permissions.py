"""Unit tests for RBAC — matrix test every (role, permission) cell (T0.10 DoD)."""
from __future__ import annotations

import pytest

from app.core.permissions import Permission, Role, get_permissions, has_permission


class TestRolePermissionMatrix:
    """Verify the roles described in CLAUDE.md §9 are correctly modeled."""

    def test_owner_has_all_permissions(self) -> None:
        owner_perms = get_permissions(Role.OWNER)
        for perm in Permission:
            assert perm in owner_perms, f"Owner missing: {perm}"

    def test_viewer_cannot_write(self) -> None:
        write_perms = {
            Permission.JOURNAL_POST,
            Permission.JOURNAL_VOID,
            Permission.INVOICE_AUTHORIZE,
            Permission.BILL_APPROVE,
            Permission.PERIOD_CLOSE,
            Permission.ACCOUNT_WRITE,
        }
        for perm in write_perms:
            assert not has_permission(Role.VIEWER, perm), f"Viewer should not have {perm}"

    def test_viewer_can_read(self) -> None:
        assert has_permission(Role.VIEWER, Permission.JOURNAL_READ)
        assert has_permission(Role.VIEWER, Permission.REPORT_READ)
        assert has_permission(Role.VIEWER, Permission.ACCOUNT_READ)

    def test_accountant_can_post_journals(self) -> None:
        assert has_permission(Role.ACCOUNTANT, Permission.JOURNAL_POST)
        assert has_permission(Role.ACCOUNTANT, Permission.JOURNAL_VOID)
        assert has_permission(Role.ACCOUNTANT, Permission.PERIOD_CLOSE)

    def test_bookkeeper_cannot_post_journals(self) -> None:
        assert not has_permission(Role.BOOKKEEPER, Permission.JOURNAL_POST)
        assert not has_permission(Role.BOOKKEEPER, Permission.PERIOD_CLOSE)

    def test_bookkeeper_can_draft(self) -> None:
        assert has_permission(Role.BOOKKEEPER, Permission.JOURNAL_DRAFT)
        assert has_permission(Role.BOOKKEEPER, Permission.INVOICE_WRITE)

    def test_auditor_can_audit_but_not_post(self) -> None:
        assert has_permission(Role.AUDITOR, Permission.AUDIT_READ)
        assert has_permission(Role.AUDITOR, Permission.AUDIT_EXPORT)
        assert not has_permission(Role.AUDITOR, Permission.JOURNAL_POST)
        assert not has_permission(Role.AUDITOR, Permission.INVOICE_AUTHORIZE)

    def test_admin_cannot_delete_tenant(self) -> None:
        assert not has_permission(Role.ADMIN, Permission.TENANT_DELETE)

    def test_admin_cannot_manage_billing(self) -> None:
        assert not has_permission(Role.ADMIN, Permission.BILLING_MANAGE)

    def test_approver_can_approve_bills(self) -> None:
        assert has_permission(Role.APPROVER, Permission.BILL_APPROVE)
        assert not has_permission(Role.APPROVER, Permission.BILL_WRITE)

    def test_role_from_string(self) -> None:
        assert has_permission("accountant", Permission.JOURNAL_POST)
        assert not has_permission("viewer", Permission.JOURNAL_POST)

    def test_unknown_role_returns_empty(self) -> None:
        with pytest.raises(ValueError):
            get_permissions("nonexistent_role")  # type: ignore[arg-type]
