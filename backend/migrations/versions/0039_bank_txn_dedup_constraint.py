"""bank_reconciliation: add dedup unique constraint on bank_transactions

Prevents duplicate bank transactions within the same bank account based on
(bank_account_id, transaction_date, amount, reference).

Revision ID: 0037
Revises: 0036
Create Date: 2026-04-18
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0039"
down_revision: str | None = "0038"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_bank_txn_dedup",
        "bank_transactions",
        ["bank_account_id", "transaction_date", "amount", "reference"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_bank_txn_dedup", "bank_transactions", type_="unique")
