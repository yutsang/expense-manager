"""bank_reconciliation: add unique constraint on journal_line_id

Revision ID: 0018
Revises: 0017
Create Date: 2026-04-16
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "CREATE UNIQUE INDEX ix_bank_txn_journal_line_unique "
        "ON bank_transactions (journal_line_id) "
        "WHERE journal_line_id IS NOT NULL"
    )


def downgrade() -> None:
    op.drop_index("ix_bank_txn_journal_line_unique", table_name="bank_transactions")
