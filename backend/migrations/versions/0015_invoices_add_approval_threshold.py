"""invoices: add invoice_approval_threshold to tenants, awaiting_approval status, authorised_by

Revision ID: 0015
Revises: 0014
Create Date: 2026-04-16
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Add invoice_approval_threshold to tenants (nullable NUMERIC)
    op.add_column(
        "tenants",
        sa.Column("invoice_approval_threshold", sa.Numeric(19, 4), nullable=True),
    )

    # Add authorised_by column to invoices
    op.add_column(
        "invoices",
        sa.Column("authorised_by", sa.UUID(), nullable=True),
    )

    # Widen invoices.status to 20 chars (was 16) to fit 'awaiting_approval'
    op.alter_column(
        "invoices",
        "status",
        type_=sa.String(20),
        existing_type=sa.String(16),
        existing_nullable=False,
    )

    # Replace the status check constraint to include 'awaiting_approval'
    op.drop_constraint("ck_invoices_status", "invoices", type_="check")
    op.create_check_constraint(
        "ck_invoices_status",
        "invoices",
        "status IN ('draft','awaiting_approval','authorised','sent','partial','paid','void','credit_note')",
    )


def downgrade() -> None:
    # Restore the original status check constraint
    op.drop_constraint("ck_invoices_status", "invoices", type_="check")
    op.create_check_constraint(
        "ck_invoices_status",
        "invoices",
        "status IN ('draft','authorised','sent','partial','paid','void','credit_note')",
    )

    # Narrow invoices.status back to 16 chars
    op.alter_column(
        "invoices",
        "status",
        type_=sa.String(16),
        existing_type=sa.String(20),
        existing_nullable=False,
    )

    # Drop the authorised_by column
    op.drop_column("invoices", "authorised_by")

    # Drop the invoice_approval_threshold column
    op.drop_column("tenants", "invoice_approval_threshold")
