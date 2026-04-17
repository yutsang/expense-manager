"""kyc: contact_ubos table for UBO / Significant Controller tracking (Cap 622)

Revision ID: 0024
Revises: 0023
Create Date: 2026-04-16
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0024"
down_revision: str | None = "0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "contact_ubos",
        sa.Column("id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("contact_id", sa.UUID(), nullable=False),
        sa.Column("controller_name", sa.String(255), nullable=False),
        sa.Column("id_type", sa.String(50), nullable=True),
        sa.Column("id_number", sa.String(100), nullable=True),
        sa.Column("nationality", sa.String(10), nullable=True),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column("ownership_pct", sa.Numeric(5, 2), nullable=False),
        sa.Column("control_type", sa.String(32), nullable=False),
        sa.Column(
            "is_significant_controller", sa.Boolean(), nullable=False, server_default="false"
        ),
        sa.Column("effective_date", sa.Date(), nullable=False),
        sa.Column("ceased_date", sa.Date(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["contact_id"], ["contacts.id"], ondelete="CASCADE"),
        sa.CheckConstraint(
            "control_type IN ('shareholding','voting_rights','board_appointment','other')",
            name="ck_contact_ubos_control_type",
        ),
        sa.CheckConstraint(
            "ownership_pct >= 0 AND ownership_pct <= 100",
            name="ck_contact_ubos_ownership_pct",
        ),
    )
    op.create_index("ix_contact_ubos_tenant", "contact_ubos", ["tenant_id"])
    op.create_index("ix_contact_ubos_contact", "contact_ubos", ["contact_id"])

    # RLS
    op.execute("ALTER TABLE contact_ubos ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE contact_ubos FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY contact_ubos_tenant ON contact_ubos
        USING (tenant_id = current_setting('app.tenant_id', true)::uuid)
        """)


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS contact_ubos_tenant ON contact_ubos")
    op.execute("ALTER TABLE contact_ubos NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE contact_ubos DISABLE ROW LEVEL SECURITY")
    op.drop_table("contact_ubos")
