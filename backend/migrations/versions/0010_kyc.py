"""kyc: contact_kyc table for KYC / sanctions tracking

Revision ID: 0010
Revises: 0009
Create Date: 2026-04-16
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "contact_kyc",
        sa.Column("id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("contact_id", sa.UUID(), nullable=False),
        sa.Column("id_type", sa.String(50), nullable=True),
        sa.Column("id_number", sa.String(100), nullable=True),
        sa.Column("id_expiry_date", sa.Date(), nullable=True),
        sa.Column("poa_type", sa.String(50), nullable=True),
        sa.Column("poa_date", sa.Date(), nullable=True),
        sa.Column("sanctions_status", sa.String(20), nullable=False, server_default="not_checked"),
        sa.Column("sanctions_checked_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("kyc_status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("kyc_approved_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("kyc_approved_by", sa.String(36), nullable=True),
        sa.Column("last_review_date", sa.Date(), nullable=True),
        sa.Column("next_review_date", sa.Date(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("created_by", sa.String(36), nullable=True),
        sa.Column("updated_by", sa.String(36), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["contact_id"], ["contacts.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("tenant_id", "contact_id", name="uq_contact_kyc_tenant_contact"),
        sa.CheckConstraint(
            "id_type IN ('passport','national_id','drivers_license','other') OR id_type IS NULL",
            name="ck_kyc_id_type",
        ),
        sa.CheckConstraint(
            "poa_type IN ('utility_bill','bank_statement','tax_document','other') OR poa_type IS NULL",
            name="ck_kyc_poa_type",
        ),
        sa.CheckConstraint(
            "sanctions_status IN ('not_checked','clear','flagged','under_review')",
            name="ck_kyc_sanctions_status",
        ),
        sa.CheckConstraint(
            "kyc_status IN ('pending','approved','expired','flagged')",
            name="ck_kyc_status",
        ),
    )
    op.create_index("ix_contact_kyc_tenant", "contact_kyc", ["tenant_id"])
    op.create_index("ix_contact_kyc_contact", "contact_kyc", ["contact_id"])

    # RLS
    op.execute("ALTER TABLE contact_kyc ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE contact_kyc FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY contact_kyc_tenant ON contact_kyc
        USING (tenant_id = current_setting('app.tenant_id', true)::uuid)
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS contact_kyc_tenant ON contact_kyc")
    op.execute("ALTER TABLE contact_kyc NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE contact_kyc DISABLE ROW LEVEL SECURITY")
    op.drop_table("contact_kyc")
