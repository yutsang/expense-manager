"""assets: change acquisition_date from String(10) to Date type

Revision ID: 0033
Revises: 0032
Create Date: 2026-04-18

Converts FixedAsset.acquisition_date from VARCHAR(10) to DATE.
Existing ISO-8601 date strings (e.g. '2025-01-15') are cast to DATE.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0033"
down_revision: str | None = "0032"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "fixed_assets",
        "acquisition_date",
        existing_type=sa.String(10),
        type_=sa.Date(),
        postgresql_using="acquisition_date::date",
        nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "fixed_assets",
        "acquisition_date",
        existing_type=sa.Date(),
        type_=sa.String(10),
        postgresql_using="to_char(acquisition_date, 'YYYY-MM-DD')",
        nullable=False,
    )
