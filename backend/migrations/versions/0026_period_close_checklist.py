"""periods: add period close checklist table

Adds period_checklist_items table for tracking sign-off of
pre-close tasks before a period can transition to soft_closed.

Revision ID: 0026
Revises: 0025
Create Date: 2026-04-16
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0026"
down_revision: str | None = "0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "period_checklist_items",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column(
            "period_id",
            sa.UUID(),
            sa.ForeignKey("periods.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("task_key", sa.String(64), nullable=False),
        sa.Column("checked_by", sa.UUID(), nullable=True),
        sa.Column("checked_at", sa.TIMESTAMP(timezone=True), nullable=True),
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
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("period_id", "task_key", name="uq_period_checklist_period_task"),
    )
    op.create_index(
        "ix_period_checklist_items_tenant_id",
        "period_checklist_items",
        ["tenant_id"],
    )
    op.create_index(
        "ix_period_checklist_items_period_id",
        "period_checklist_items",
        ["period_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_period_checklist_items_period_id", table_name="period_checklist_items")
    op.drop_index("ix_period_checklist_items_tenant_id", table_name="period_checklist_items")
    op.drop_table("period_checklist_items")
