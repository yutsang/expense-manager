"""ledger: add accruals table for accruals and prepayments

Creates the accruals table with automatic reversal support.
Each accrual links to an initial JE and optionally a reversal JE.

Revision ID: 0029
Revises: 0028
Create Date: 2026-04-16
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0029"
down_revision: str | None = "0028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "accruals",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("accrual_type", sa.String(16), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("amount", sa.Numeric(19, 4), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="USD"),
        sa.Column(
            "debit_account_id",
            sa.UUID(),
            sa.ForeignKey("accounts.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "credit_account_id",
            sa.UUID(),
            sa.ForeignKey("accounts.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "period_id",
            sa.UUID(),
            sa.ForeignKey("periods.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "journal_entry_id",
            sa.UUID(),
            sa.ForeignKey("journal_entries.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "reversal_journal_entry_id",
            sa.UUID(),
            sa.ForeignKey("journal_entries.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("status", sa.String(16), nullable=False, server_default="posted"),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "accrual_type IN ('accrual','prepayment')", name="ck_accruals_type"
        ),
        sa.CheckConstraint("status IN ('posted','reversed')", name="ck_accruals_status"),
        sa.CheckConstraint("amount > 0", name="ck_accruals_positive"),
    )
    op.create_index("ix_accruals_tenant_id", "accruals", ["tenant_id"])
    op.create_index("ix_accruals_period_id", "accruals", ["period_id"])


def downgrade() -> None:
    op.drop_index("ix_accruals_period_id", table_name="accruals")
    op.drop_index("ix_accruals_tenant_id", table_name="accruals")
    op.drop_table("accruals")
