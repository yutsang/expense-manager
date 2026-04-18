"""schema: add tenant_id foreign key constraints on 11 tables

Revision ID: 0040
Revises: 0039
Create Date: 2026-04-18

Adds FK constraint tenant_id -> tenants.id (ON DELETE RESTRICT) to:
attachments, receipts, sales_documents, sales_document_lines,
purchase_orders, purchase_order_lines, ai_conversations, ai_messages,
accruals, fixed_assets, salary_records.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0042"
down_revision: str | None = "0041"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = [
    "attachments",
    "receipts",
    "sales_documents",
    "sales_document_lines",
    "purchase_orders",
    "purchase_order_lines",
    "ai_conversations",
    "ai_messages",
    "accruals",
    "fixed_assets",
    "salary_records",
]


def upgrade() -> None:
    for table in _TABLES:
        op.create_foreign_key(
            f"fk_{table}_tenant_id",
            table,
            "tenants",
            ["tenant_id"],
            ["id"],
            ondelete="RESTRICT",
        )


def downgrade() -> None:
    for table in reversed(_TABLES):
        op.drop_constraint(f"fk_{table}_tenant_id", table, type_="foreignkey")
