"""receipts: receipt OCR table for bill drafting

Revision ID: 0012
Revises: 0011
Create Date: 2026-04-16
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "receipts",
        sa.Column("id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("s3_key", sa.String(512), nullable=False),
        sa.Column("content_type", sa.String(100), nullable=False),
        sa.Column("file_size_kb", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("ocr_vendor", sa.String(255), nullable=True),
        sa.Column("ocr_date", sa.String(10), nullable=True),
        sa.Column("ocr_currency", sa.String(3), nullable=True),
        sa.Column("ocr_total", sa.Numeric(19, 4), nullable=True),
        sa.Column("ocr_raw", JSONB(), nullable=False, server_default="'{}'"),
        sa.Column("linked_bill_id", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("created_by", sa.String(36), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["linked_bill_id"],
            ["bills.id"],
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            "status IN ('pending','processing','done','failed','deleted')",
            name="ck_receipts_status",
        ),
    )
    op.create_index("ix_receipts_tenant_id", "receipts", ["tenant_id"])

    # Row-Level Security
    op.execute("ALTER TABLE receipts ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY receipts_tenant_isolation ON receipts
        USING (tenant_id = current_setting('app.tenant_id', true)::uuid)
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS receipts_tenant_isolation ON receipts")
    op.execute("ALTER TABLE receipts DISABLE ROW LEVEL SECURITY")
    op.drop_index("ix_receipts_tenant_id", table_name="receipts")
    op.drop_table("receipts")
