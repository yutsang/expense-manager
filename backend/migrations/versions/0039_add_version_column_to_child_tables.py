"""schema: add version column for optimistic locking on 9 child/line tables

Revision ID: 0039
Revises: 0038
Create Date: 2026-04-18

Adds version INTEGER NOT NULL DEFAULT 1 to: invoice_lines, bill_lines,
journal_lines, expense_claim_lines, payment_allocations,
sales_document_lines, purchase_order_lines, sync_devices, sync_ops.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0039"
down_revision: str | None = "0038"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = [
    "invoice_lines",
    "bill_lines",
    "journal_lines",
    "expense_claim_lines",
    "payment_allocations",
    "sales_document_lines",
    "purchase_order_lines",
    "sync_devices",
    "sync_ops",
]


def upgrade() -> None:
    for table in _TABLES:
        op.add_column(
            table,
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        )


def downgrade() -> None:
    for table in reversed(_TABLES):
        op.drop_column(table, "version")
