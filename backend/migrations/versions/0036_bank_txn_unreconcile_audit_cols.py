"""bank_reconciliation: add unreconcile audit columns to bank_transactions

Adds unreconciled_at, unreconciled_by, unreconcile_reason to track
when and why a bank transaction was un-reconciled.

Revision ID: 0036
Revises: 0035
Create Date: 2026-04-18
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0036"
down_revision: str | None = "0035"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "bank_transactions",
        sa.Column("unreconciled_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.add_column(
        "bank_transactions",
        sa.Column("unreconciled_by", sa.UUID(), nullable=True),
    )
    op.add_column(
        "bank_transactions",
        sa.Column("unreconcile_reason", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("bank_transactions", "unreconcile_reason")
    op.drop_column("bank_transactions", "unreconciled_by")
    op.drop_column("bank_transactions", "unreconciled_at")
