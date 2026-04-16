"""sales_chain: sales_documents, purchase_orders, attachments

Revision ID: 0014
Revises: 0013
Create Date: 2026-04-16
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- sales_documents -------------------------------------------------------
    op.create_table(
        "sales_documents",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("doc_type", sa.String(20), nullable=False),
        sa.Column("number", sa.String(50), nullable=False),
        sa.Column("contact_id", sa.UUID(), nullable=True),
        sa.Column("issue_date", sa.String(10), nullable=False),
        sa.Column("expiry_date", sa.String(10), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'draft'")),
        sa.Column("currency", sa.String(3), nullable=False, server_default=sa.text("'USD'")),
        sa.Column("subtotal", sa.Numeric(19, 4), nullable=False, server_default="0"),
        sa.Column("tax_total", sa.Numeric(19, 4), nullable=False, server_default="0"),
        sa.Column("total", sa.Numeric(19, 4), nullable=False, server_default="0"),
        sa.Column("reference", sa.String(200), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("converted_to_id", sa.String(36), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.Column("locked", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "doc_type IN ('quote','sales_order')",
            name="ck_sales_documents_type",
        ),
        sa.CheckConstraint(
            "status IN ('draft','sent','accepted','rejected','converted','voided')",
            name="ck_sales_documents_status",
        ),
        sa.UniqueConstraint("tenant_id", "number", name="uq_sales_documents_tenant_number"),
        sa.ForeignKeyConstraint(["contact_id"], ["contacts.id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_sales_documents_tenant_id", "sales_documents", ["tenant_id"])
    op.create_index("ix_sales_documents_contact_id", "sales_documents", ["contact_id"])

    # --- sales_document_lines --------------------------------------------------
    op.create_table(
        "sales_document_lines",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("document_id", sa.UUID(), nullable=False),
        sa.Column("item_id", sa.UUID(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("quantity", sa.Numeric(19, 4), nullable=False, server_default="1"),
        sa.Column("unit_price", sa.Numeric(19, 4), nullable=False, server_default="0"),
        sa.Column("tax_rate", sa.Numeric(7, 4), nullable=False, server_default="0"),
        sa.Column("line_total", sa.Numeric(19, 4), nullable=False, server_default="0"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["document_id"], ["sales_documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["item_id"], ["items.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_sales_document_lines_tenant_id", "sales_document_lines", ["tenant_id"])
    op.create_index("ix_sales_document_lines_document_id", "sales_document_lines", ["document_id"])

    # --- purchase_orders -------------------------------------------------------
    op.create_table(
        "purchase_orders",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("number", sa.String(50), nullable=False),
        sa.Column("contact_id", sa.UUID(), nullable=True),
        sa.Column("issue_date", sa.String(10), nullable=False),
        sa.Column("expected_delivery", sa.String(10), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'draft'")),
        sa.Column("currency", sa.String(3), nullable=False, server_default=sa.text("'USD'")),
        sa.Column("subtotal", sa.Numeric(19, 4), nullable=False, server_default="0"),
        sa.Column("tax_total", sa.Numeric(19, 4), nullable=False, server_default="0"),
        sa.Column("total", sa.Numeric(19, 4), nullable=False, server_default="0"),
        sa.Column("reference", sa.String(200), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("linked_bill_id", sa.String(36), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.Column("locked", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "status IN ('draft','sent','partially_received','received','billed','voided')",
            name="ck_purchase_orders_status",
        ),
        sa.UniqueConstraint("tenant_id", "number", name="uq_purchase_orders_tenant_number"),
        sa.ForeignKeyConstraint(["contact_id"], ["contacts.id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_purchase_orders_tenant_id", "purchase_orders", ["tenant_id"])
    op.create_index("ix_purchase_orders_contact_id", "purchase_orders", ["contact_id"])

    # --- purchase_order_lines --------------------------------------------------
    op.create_table(
        "purchase_order_lines",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("po_id", sa.UUID(), nullable=False),
        sa.Column("item_id", sa.UUID(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("quantity", sa.Numeric(19, 4), nullable=False, server_default="1"),
        sa.Column("unit_price", sa.Numeric(19, 4), nullable=False, server_default="0"),
        sa.Column("tax_rate", sa.Numeric(7, 4), nullable=False, server_default="0"),
        sa.Column("line_total", sa.Numeric(19, 4), nullable=False, server_default="0"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["po_id"], ["purchase_orders.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["item_id"], ["items.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_purchase_order_lines_tenant_id", "purchase_order_lines", ["tenant_id"])
    op.create_index("ix_purchase_order_lines_po_id", "purchase_order_lines", ["po_id"])

    # --- attachments -----------------------------------------------------------
    op.create_table(
        "attachments",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("entity_type", sa.String(50), nullable=False),
        sa.Column("entity_id", sa.String(36), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("s3_key", sa.String(500), nullable=False),
        sa.Column("content_type", sa.String(100), nullable=False),
        sa.Column("file_size_kb", sa.Integer(), nullable=False),
        sa.Column("uploaded_by", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_attachments_tenant_id", "attachments", ["tenant_id"])
    op.create_index("ix_attachments_entity_id", "attachments", ["entity_id"])


def downgrade() -> None:
    op.drop_table("attachments")
    op.drop_table("purchase_order_lines")
    op.drop_table("purchase_orders")
    op.drop_table("sales_document_lines")
    op.drop_table("sales_documents")
