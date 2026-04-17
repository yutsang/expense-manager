"""ledger: add journal maker-checker columns and tenant approval flag

Adds submitted_by, submitted_at, approved_by, approved_at to journal_entries.
Updates the status CHECK constraint to include 'awaiting_approval'.
Adds journal_approval_required boolean to tenants.

Revision ID: 0025
Revises: 0024
Create Date: 2026-04-16
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0025"
down_revision: str | None = "0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # -- journal_entries: new columns -------------------------------------------
    op.add_column(
        "journal_entries",
        sa.Column("submitted_by", sa.UUID(), nullable=True),
    )
    op.add_column(
        "journal_entries",
        sa.Column("submitted_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.add_column(
        "journal_entries",
        sa.Column("approved_by", sa.UUID(), nullable=True),
    )
    op.add_column(
        "journal_entries",
        sa.Column("approved_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )

    # -- journal_entries: update status CHECK to include awaiting_approval ------
    op.drop_constraint("ck_je_status", "journal_entries", type_="check")
    op.create_check_constraint(
        "ck_je_status",
        "journal_entries",
        "status IN ('draft','awaiting_approval','posted','void')",
    )

    # -- tenants: add journal_approval_required --------------------------------
    op.add_column(
        "tenants",
        sa.Column(
            "journal_approval_required",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )


def downgrade() -> None:
    # -- tenants: drop journal_approval_required --------------------------------
    op.drop_column("tenants", "journal_approval_required")

    # -- journal_entries: revert status CHECK -----------------------------------
    op.drop_constraint("ck_je_status", "journal_entries", type_="check")
    op.create_check_constraint(
        "ck_je_status",
        "journal_entries",
        "status IN ('draft','posted','void')",
    )

    # -- journal_entries: drop new columns -------------------------------------
    op.drop_column("journal_entries", "approved_at")
    op.drop_column("journal_entries", "approved_by")
    op.drop_column("journal_entries", "submitted_at")
    op.drop_column("journal_entries", "submitted_by")
