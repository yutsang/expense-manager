"""invoices: add last_reminder_sent_at and reminder_count columns

Revision ID: 0013
Revises: 0012
Create Date: 2026-04-16
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "invoices",
        sa.Column("last_reminder_sent_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.add_column(
        "invoices",
        sa.Column(
            "reminder_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )


def downgrade() -> None:
    op.drop_column("invoices", "reminder_count")
    op.drop_column("invoices", "last_reminder_sent_at")
