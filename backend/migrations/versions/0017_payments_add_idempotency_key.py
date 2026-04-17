"""payments: add idempotency_key

Revision ID: 0017
Revises: 0016
Create Date: 2026-04-16
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "payments",
        sa.Column("idempotency_key", sa.String(256), nullable=True),
    )
    op.create_index(
        "ix_payments_idempotency",
        "payments",
        ["tenant_id", "idempotency_key"],
    )


def downgrade() -> None:
    op.drop_index("ix_payments_idempotency", table_name="payments")
    op.drop_column("payments", "idempotency_key")
