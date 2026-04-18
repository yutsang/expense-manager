"""invoices: add invoice_templates table for recurring invoices

Revision ID: 0046
Revises: 0045
Create Date: 2026-04-18
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0046"
down_revision: str | None = "0045"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "invoice_templates",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "tenant_id",
            sa.UUID(),
            sa.ForeignKey("tenants.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "contact_id",
            sa.UUID(),
            sa.ForeignKey("contacts.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="USD"),
        sa.Column("lines_json", JSONB(), nullable=False, server_default="[]"),
        sa.Column("recurrence_frequency", sa.String(20), nullable=True),
        sa.Column("next_generation_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("last_generated_invoice_id", sa.String(36), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "recurrence_frequency IN ('weekly','monthly','quarterly','annually') "
            "OR recurrence_frequency IS NULL",
            name="ck_invoice_templates_frequency",
        ),
    )
    op.create_index("ix_invoice_templates_tenant_id", "invoice_templates", ["tenant_id"])
    op.create_index("ix_invoice_templates_contact_id", "invoice_templates", ["contact_id"])


def downgrade() -> None:
    op.drop_index("ix_invoice_templates_contact_id", table_name="invoice_templates")
    op.drop_index("ix_invoice_templates_tenant_id", table_name="invoice_templates")
    op.drop_table("invoice_templates")
