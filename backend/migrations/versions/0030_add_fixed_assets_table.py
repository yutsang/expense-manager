"""assets: add fixed_assets table for depreciation tracking

Revision ID: 0030
Revises: 0029
Create Date: 2026-04-16
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0030"
down_revision: str | None = "0029"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "fixed_assets",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("acquisition_date", sa.String(10), nullable=False),
        sa.Column("cost", sa.Numeric(19, 4), nullable=False),
        sa.Column("residual_value", sa.Numeric(19, 4), nullable=False, server_default="0"),
        sa.Column("useful_life_months", sa.Integer(), nullable=False),
        sa.Column("depreciation_method", sa.String(20), nullable=False),
        sa.Column(
            "asset_account_id",
            sa.UUID(),
            sa.ForeignKey("accounts.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "depreciation_account_id",
            sa.UUID(),
            sa.ForeignKey("accounts.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "accumulated_depreciation_account_id",
            sa.UUID(),
            sa.ForeignKey("accounts.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("description", sa.Text(), nullable=True),
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
            "category IN ('equipment','vehicle','furniture','leasehold_improvement','other')",
            name="ck_fixed_assets_category",
        ),
        sa.CheckConstraint(
            "depreciation_method IN ('straight_line','declining_balance')",
            name="ck_fixed_assets_depr_method",
        ),
        sa.CheckConstraint(
            "status IN ('active','disposed','fully_depreciated')",
            name="ck_fixed_assets_status",
        ),
        sa.CheckConstraint("cost > 0", name="ck_fixed_assets_cost_positive"),
        sa.CheckConstraint("residual_value >= 0", name="ck_fixed_assets_residual_non_negative"),
        sa.CheckConstraint("useful_life_months > 0", name="ck_fixed_assets_life_positive"),
    )
    op.create_index("ix_fixed_assets_tenant_id", "fixed_assets", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("ix_fixed_assets_tenant_id", table_name="fixed_assets")
    op.drop_table("fixed_assets")
