"""tenant-settings: add settings JSONB, tax_rounding_policy, is_tax_inclusive

Adds:
- tenants.settings (JSONB, NOT NULL DEFAULT '{}')
- tenants.tax_rounding_policy (VARCHAR(16), NOT NULL DEFAULT 'per_line')
- invoices.is_tax_inclusive (BOOLEAN, NOT NULL DEFAULT FALSE)
- bills.is_tax_inclusive (BOOLEAN, NOT NULL DEFAULT FALSE)

Revision ID: 0036
Revises: 0035
Create Date: 2026-04-18
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0038"
down_revision: str | None = "0037"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Tenant columns
    op.add_column(
        "tenants",
        sa.Column("settings", JSONB, nullable=False, server_default="{}"),
    )
    op.add_column(
        "tenants",
        sa.Column(
            "tax_rounding_policy",
            sa.String(16),
            nullable=False,
            server_default="per_line",
        ),
    )

    # Invoice / Bill tax-inclusive flag
    op.add_column(
        "invoices",
        sa.Column("is_tax_inclusive", sa.Boolean, nullable=False, server_default="false"),
    )
    op.add_column(
        "bills",
        sa.Column("is_tax_inclusive", sa.Boolean, nullable=False, server_default="false"),
    )


def downgrade() -> None:
    op.drop_column("bills", "is_tax_inclusive")
    op.drop_column("invoices", "is_tax_inclusive")
    op.drop_column("tenants", "tax_rounding_policy")
    op.drop_column("tenants", "settings")
