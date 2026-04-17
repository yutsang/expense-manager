"""invoices: add share_token, viewed_at, acknowledged_at for customer portal

Adds columns for the shareable invoice portal feature:
- share_token: unique token for public access
- viewed_at: when the customer first viewed the invoice
- acknowledged_at: when the customer acknowledged receipt
- acknowledged_by_name: name provided by customer on acknowledge

Revision ID: 0028
Revises: 0027
Create Date: 2026-04-16
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0028"
down_revision: str | None = "0027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "invoices",
        sa.Column("share_token", sa.String(256), nullable=True),
    )
    op.add_column(
        "invoices",
        sa.Column("viewed_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.add_column(
        "invoices",
        sa.Column("acknowledged_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.add_column(
        "invoices",
        sa.Column("acknowledged_by_name", sa.String(255), nullable=True),
    )
    op.create_index(
        "ix_invoices_share_token",
        "invoices",
        ["share_token"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_invoices_share_token", table_name="invoices")
    op.drop_column("invoices", "acknowledged_by_name")
    op.drop_column("invoices", "acknowledged_at")
    op.drop_column("invoices", "viewed_at")
    op.drop_column("invoices", "share_token")
