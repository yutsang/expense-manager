"""budgets: add budgets and budget_lines tables

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
    op.create_table(
        "budgets",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "tenant_id",
            sa.UUID(),
            sa.ForeignKey("tenants.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("fiscal_year", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
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
            "status IN ('draft','active','closed')",
            name="ck_budgets_status",
        ),
    )
    op.create_index("ix_budgets_tenant_id", "budgets", ["tenant_id"])

    op.create_table(
        "budget_lines",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "tenant_id",
            sa.UUID(),
            sa.ForeignKey("tenants.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "budget_id",
            sa.UUID(),
            sa.ForeignKey("budgets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "account_id",
            sa.UUID(),
            sa.ForeignKey("accounts.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("month_1", sa.Numeric(19, 4), nullable=False, server_default="0"),
        sa.Column("month_2", sa.Numeric(19, 4), nullable=False, server_default="0"),
        sa.Column("month_3", sa.Numeric(19, 4), nullable=False, server_default="0"),
        sa.Column("month_4", sa.Numeric(19, 4), nullable=False, server_default="0"),
        sa.Column("month_5", sa.Numeric(19, 4), nullable=False, server_default="0"),
        sa.Column("month_6", sa.Numeric(19, 4), nullable=False, server_default="0"),
        sa.Column("month_7", sa.Numeric(19, 4), nullable=False, server_default="0"),
        sa.Column("month_8", sa.Numeric(19, 4), nullable=False, server_default="0"),
        sa.Column("month_9", sa.Numeric(19, 4), nullable=False, server_default="0"),
        sa.Column("month_10", sa.Numeric(19, 4), nullable=False, server_default="0"),
        sa.Column("month_11", sa.Numeric(19, 4), nullable=False, server_default="0"),
        sa.Column("month_12", sa.Numeric(19, 4), nullable=False, server_default="0"),
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
        sa.UniqueConstraint("budget_id", "account_id", name="uq_budget_lines_budget_account"),
    )
    op.create_index("ix_budget_lines_tenant_id", "budget_lines", ["tenant_id"])
    op.create_index("ix_budget_lines_budget_id", "budget_lines", ["budget_id"])
    op.create_index("ix_budget_lines_account_id", "budget_lines", ["account_id"])


def downgrade() -> None:
    op.drop_index("ix_budget_lines_account_id", table_name="budget_lines")
    op.drop_index("ix_budget_lines_budget_id", table_name="budget_lines")
    op.drop_index("ix_budget_lines_tenant_id", table_name="budget_lines")
    op.drop_table("budget_lines")
    op.drop_index("ix_budgets_tenant_id", table_name="budgets")
    op.drop_table("budgets")
