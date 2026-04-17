"""contacts: add credit_limit

Revision ID: 0021
Revises: 0020
Create Date: 2026-04-16
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0021"
down_revision: str | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "contacts",
        sa.Column("credit_limit", sa.Numeric(19, 4), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("contacts", "credit_limit")
