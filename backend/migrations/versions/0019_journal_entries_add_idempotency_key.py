"""journal_entries: add idempotency_key

Revision ID: 0019
Revises: 0018
Create Date: 2026-04-16
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "journal_entries",
        sa.Column("idempotency_key", sa.String(256), nullable=True),
    )
    op.create_index(
        "ix_je_idempotency",
        "journal_entries",
        ["tenant_id", "idempotency_key"],
    )


def downgrade() -> None:
    op.drop_index("ix_je_idempotency", table_name="journal_entries")
    op.drop_column("journal_entries", "idempotency_key")
