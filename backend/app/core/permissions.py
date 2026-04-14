"""Role-Based Access Control.

Roles and permissions as defined in CLAUDE.md §9.

Usage in FastAPI routes:
    @router.post("/journals/{id}/post")
    async def post_journal(
        _: None = Depends(require(Permission.JOURNAL_POST)),
    ) -> ...:
"""
from __future__ import annotations

from enum import StrEnum


class Role(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    ACCOUNTANT = "accountant"
    BOOKKEEPER = "bookkeeper"
    APPROVER = "approver"
    VIEWER = "viewer"
    AUDITOR = "auditor"
    API_CLIENT = "api_client"


class Permission(StrEnum):
    # Tenant
    TENANT_MANAGE = "tenant:manage"
    TENANT_DELETE = "tenant:delete"
    BILLING_MANAGE = "billing:manage"

    # Users / memberships
    USER_INVITE = "user:invite"
    USER_MANAGE = "user:manage"
    ROLE_ASSIGN = "role:assign"

    # Ledger — read
    JOURNAL_READ = "journal:read"
    REPORT_READ = "report:read"
    ACCOUNT_READ = "account:read"
    PERIOD_READ = "period:read"

    # Ledger — write
    ACCOUNT_WRITE = "account:write"
    JOURNAL_DRAFT = "journal:draft"
    JOURNAL_POST = "journal:post"
    JOURNAL_VOID = "journal:void"
    PERIOD_CLOSE = "period:close"
    PERIOD_REOPEN = "period:reopen"

    # AR / AP / Banking
    INVOICE_WRITE = "invoice:write"
    INVOICE_AUTHORIZE = "invoice:authorize"
    BILL_WRITE = "bill:write"
    BILL_APPROVE = "bill:approve"
    PAYMENT_WRITE = "payment:write"
    BANK_MANAGE = "bank:manage"
    RECONCILIATION_WRITE = "reconciliation:write"

    # Contacts / items
    CONTACT_WRITE = "contact:write"
    ITEM_WRITE = "item:write"

    # Tax
    TAX_WRITE = "tax:write"

    # Audit
    AUDIT_READ = "audit:read"
    AUDIT_EXPORT = "audit:export"
    AUDIT_VERIFY = "audit:verify"

    # AI
    AI_CHAT = "ai:chat"
    AI_MUTATE_CONFIRM = "ai:mutate_confirm"

    # Feature flags (admin)
    FEATURE_FLAG_MANAGE = "feature_flag:manage"


# Role → granted permissions. Higher roles include lower roles' permissions.
_ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.VIEWER: frozenset({
        Permission.JOURNAL_READ,
        Permission.REPORT_READ,
        Permission.ACCOUNT_READ,
        Permission.PERIOD_READ,
        Permission.AI_CHAT,
    }),
    Role.APPROVER: frozenset({
        Permission.JOURNAL_READ,
        Permission.REPORT_READ,
        Permission.ACCOUNT_READ,
        Permission.PERIOD_READ,
        Permission.BILL_APPROVE,
        Permission.AI_CHAT,
    }),
    Role.AUDITOR: frozenset({
        Permission.JOURNAL_READ,
        Permission.REPORT_READ,
        Permission.ACCOUNT_READ,
        Permission.PERIOD_READ,
        Permission.AUDIT_READ,
        Permission.AUDIT_EXPORT,
        Permission.AUDIT_VERIFY,
        Permission.AI_CHAT,
        Permission.PERIOD_REOPEN,
    }),
    Role.BOOKKEEPER: frozenset({
        Permission.JOURNAL_READ,
        Permission.REPORT_READ,
        Permission.ACCOUNT_READ,
        Permission.PERIOD_READ,
        Permission.JOURNAL_DRAFT,
        Permission.INVOICE_WRITE,
        Permission.BILL_WRITE,
        Permission.CONTACT_WRITE,
        Permission.ITEM_WRITE,
        Permission.PAYMENT_WRITE,
        Permission.AI_CHAT,
        Permission.AI_MUTATE_CONFIRM,
    }),
    Role.ACCOUNTANT: frozenset({
        Permission.JOURNAL_READ,
        Permission.REPORT_READ,
        Permission.ACCOUNT_READ,
        Permission.PERIOD_READ,
        Permission.AUDIT_READ,
        Permission.JOURNAL_DRAFT,
        Permission.JOURNAL_POST,
        Permission.JOURNAL_VOID,
        Permission.PERIOD_CLOSE,
        Permission.INVOICE_WRITE,
        Permission.INVOICE_AUTHORIZE,
        Permission.BILL_WRITE,
        Permission.BILL_APPROVE,
        Permission.PAYMENT_WRITE,
        Permission.BANK_MANAGE,
        Permission.RECONCILIATION_WRITE,
        Permission.CONTACT_WRITE,
        Permission.ITEM_WRITE,
        Permission.TAX_WRITE,
        Permission.ACCOUNT_WRITE,
        Permission.AI_CHAT,
        Permission.AI_MUTATE_CONFIRM,
    }),
    Role.ADMIN: frozenset({p for p in Permission} - {
        Permission.BILLING_MANAGE,
        Permission.TENANT_DELETE,
    }),
    Role.OWNER: frozenset({p for p in Permission}),
}


def get_permissions(role: Role | str) -> frozenset[Permission]:
    r = Role(role) if isinstance(role, str) else role
    return _ROLE_PERMISSIONS.get(r, frozenset())


def has_permission(role: Role | str, permission: Permission) -> bool:
    return permission in get_permissions(role)
