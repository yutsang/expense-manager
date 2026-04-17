"""tenants: add setup_completed_at for onboarding wizard

Adds setup_completed_at nullable timestamp column to tenants table.
When NULL, the tenant has not completed the onboarding wizard.

Revision ID: 0027
Revises: 0026
Create Date: 2026-04-16
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0027"
down_revision: str | None = "0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tenants",
        sa.Column("setup_completed_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("tenants", "setup_completed_at")
