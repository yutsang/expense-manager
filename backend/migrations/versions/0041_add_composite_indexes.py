"""schema: add composite indexes for common query patterns

Revision ID: 0041
Revises: 0040
Create Date: 2026-04-18

Adds composite indexes on:
  - journal_entries (tenant_id, status, date)
  - journal_lines (account_id, tenant_id)
  - bank_transactions (bank_account_id, is_reconciled, transaction_date)
  - invoices (tenant_id, contact_id, status)
  - bills (tenant_id, contact_id, status)
  - payments (tenant_id, contact_id, status)
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0041"
down_revision: str | None = "0040"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_INDEXES = [
    ("ix_je_tenant_status_date", "journal_entries", ["tenant_id", "status", "date"]),
    ("ix_jl_account_tenant", "journal_lines", ["account_id", "tenant_id"]),
    (
        "ix_bank_txn_acct_reconciled_date",
        "bank_transactions",
        ["bank_account_id", "is_reconciled", "transaction_date"],
    ),
    ("ix_invoices_tenant_contact_status", "invoices", ["tenant_id", "contact_id", "status"]),
    ("ix_bills_tenant_contact_status", "bills", ["tenant_id", "contact_id", "status"]),
    ("ix_payments_tenant_contact_status", "payments", ["tenant_id", "contact_id", "status"]),
]


def upgrade() -> None:
    for name, table, columns in _INDEXES:
        op.create_index(name, table, columns)


def downgrade() -> None:
    for name, table, _columns in reversed(_INDEXES):
        op.drop_index(name, table_name=table)
