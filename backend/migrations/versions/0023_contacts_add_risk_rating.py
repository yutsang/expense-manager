"""contacts: add AMLO Cap 615 risk rating and EDD fields

Revision ID: 0023
Revises: 0022
Create Date: 2026-04-18
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0023"
down_revision: str | None = "0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "contacts",
        sa.Column("risk_rating", sa.String(16), nullable=True),
    )
    op.add_column(
        "contacts",
        sa.Column("risk_rating_rationale", sa.Text(), nullable=True),
    )
    op.add_column(
        "contacts",
        sa.Column("risk_rated_by", sa.dialects.postgresql.UUID(as_uuid=False), nullable=True),
    )
    op.add_column(
        "contacts",
        sa.Column("risk_rated_at", sa.dialects.postgresql.TIMESTAMP(timezone=True), nullable=True),
    )
    op.add_column(
        "contacts",
        sa.Column("edd_required", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "contacts",
        sa.Column("edd_approved_by", sa.dialects.postgresql.UUID(as_uuid=False), nullable=True),
    )
    op.add_column(
        "contacts",
        sa.Column(
            "edd_approved_at", sa.dialects.postgresql.TIMESTAMP(timezone=True), nullable=True
        ),
    )
    op.create_check_constraint(
        "ck_contacts_risk_rating",
        "contacts",
        "risk_rating IN ('low','medium','high','unacceptable') OR risk_rating IS NULL",
    )


def downgrade() -> None:
    op.drop_constraint("ck_contacts_risk_rating", "contacts", type_="check")
    op.drop_column("contacts", "edd_approved_at")
    op.drop_column("contacts", "edd_approved_by")
    op.drop_column("contacts", "edd_required")
    op.drop_column("contacts", "risk_rated_at")
    op.drop_column("contacts", "risk_rated_by")
    op.drop_column("contacts", "risk_rating_rationale")
    op.drop_column("contacts", "risk_rating")
