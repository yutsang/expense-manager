"""transactions: contacts items tax_codes invoices bills payments

Revision ID: 0004
Revises: 0003
Create Date: 2026-04-14
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- contacts -----------------------------------------------------------
    op.create_table(
        "contacts",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("contact_type", sa.String(16), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("code", sa.String(64), nullable=True),
        sa.Column("email", sa.String(254), nullable=True),
        sa.Column("phone", sa.String(40), nullable=True),
        sa.Column("currency", sa.String(3), nullable=False, server_default="USD"),
        sa.Column("tax_number", sa.String(64), nullable=True),
        sa.Column("address_line1", sa.String(255), nullable=True),
        sa.Column("address_line2", sa.String(255), nullable=True),
        sa.Column("city", sa.String(100), nullable=True),
        sa.Column("region", sa.String(100), nullable=True),
        sa.Column("postal_code", sa.String(20), nullable=True),
        sa.Column("country", sa.String(10), nullable=True),
        sa.Column("is_archived", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "contact_type IN ('customer','supplier','both','employee')",
            name="ck_contacts_type",
        ),
        sa.UniqueConstraint("tenant_id", "code", name="uq_contacts_tenant_code"),
    )
    op.create_index("ix_contacts_tenant_id", "contacts", ["tenant_id"])

    # --- items --------------------------------------------------------------
    op.create_table(
        "items",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("item_type", sa.String(16), nullable=False),
        sa.Column("unit_of_measure", sa.String(32), nullable=True),
        sa.Column("sales_unit_price", sa.Numeric(19, 4), nullable=True),
        sa.Column("purchase_unit_price", sa.Numeric(19, 4), nullable=True),
        sa.Column("currency", sa.String(3), nullable=False, server_default="USD"),
        sa.Column("sales_account_id", sa.UUID(), nullable=True),
        sa.Column("cogs_account_id", sa.UUID(), nullable=True),
        sa.Column("purchase_account_id", sa.UUID(), nullable=True),
        sa.Column("is_tracked", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("is_archived", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("item_type IN ('product','service')", name="ck_items_type"),
        sa.UniqueConstraint("tenant_id", "code", name="uq_items_tenant_code"),
        sa.ForeignKeyConstraint(["sales_account_id"], ["accounts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["cogs_account_id"], ["accounts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["purchase_account_id"], ["accounts.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_items_tenant_id", "items", ["tenant_id"])

    # --- tax_codes ----------------------------------------------------------
    op.create_table(
        "tax_codes",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("code", sa.String(32), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("rate", sa.Numeric(8, 6), nullable=False),
        sa.Column("tax_type", sa.String(16), nullable=False),
        sa.Column("country", sa.String(10), nullable=False),
        sa.Column("tax_collected_account_id", sa.UUID(), nullable=True),
        sa.Column("tax_paid_account_id", sa.UUID(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "tax_type IN ('output','input','exempt','zero')",
            name="ck_tax_codes_type",
        ),
        sa.CheckConstraint("rate >= 0 AND rate <= 1", name="ck_tax_codes_rate"),
        sa.UniqueConstraint("tenant_id", "code", name="uq_tax_codes_tenant_code"),
        sa.ForeignKeyConstraint(["tax_collected_account_id"], ["accounts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tax_paid_account_id"], ["accounts.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_tax_codes_tenant_id", "tax_codes", ["tenant_id"])

    # --- invoices -----------------------------------------------------------
    op.create_table(
        "invoices",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("number", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
        sa.Column("contact_id", sa.UUID(), nullable=False),
        sa.Column("issue_date", sa.String(10), nullable=False),
        sa.Column("due_date", sa.String(10), nullable=True),
        sa.Column("period_name", sa.String(7), nullable=True),
        sa.Column("reference", sa.String(128), nullable=True),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("fx_rate", sa.Numeric(19, 8), nullable=False, server_default="1"),
        sa.Column("subtotal", sa.Numeric(19, 4), nullable=False, server_default="0"),
        sa.Column("tax_total", sa.Numeric(19, 4), nullable=False, server_default="0"),
        sa.Column("total", sa.Numeric(19, 4), nullable=False, server_default="0"),
        sa.Column("amount_due", sa.Numeric(19, 4), nullable=False, server_default="0"),
        sa.Column("functional_total", sa.Numeric(19, 4), nullable=False, server_default="0"),
        sa.Column("journal_entry_id", sa.UUID(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("sent_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("paid_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("voided_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "status IN ('draft','authorised','sent','partial','paid','void','credit_note')",
            name="ck_invoices_status",
        ),
        sa.UniqueConstraint("tenant_id", "number", name="uq_invoices_tenant_number"),
        sa.ForeignKeyConstraint(["contact_id"], ["contacts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["journal_entry_id"], ["journal_entries.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_invoices_tenant_id", "invoices", ["tenant_id"])
    op.create_index("ix_invoices_contact_id", "invoices", ["contact_id"])

    # --- invoice_lines ------------------------------------------------------
    op.create_table(
        "invoice_lines",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("invoice_id", sa.UUID(), nullable=False),
        sa.Column("line_no", sa.SmallInteger(), nullable=False),
        sa.Column("item_id", sa.UUID(), nullable=True),
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column("tax_code_id", sa.UUID(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("quantity", sa.Numeric(19, 4), nullable=False, server_default="1"),
        sa.Column("unit_price", sa.Numeric(19, 4), nullable=False, server_default="0"),
        sa.Column("discount_pct", sa.Numeric(5, 4), nullable=False, server_default="0"),
        sa.Column("line_amount", sa.Numeric(19, 4), nullable=False, server_default="0"),
        sa.Column("tax_amount", sa.Numeric(19, 4), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("quantity > 0", name="ck_invline_qty"),
        sa.CheckConstraint("discount_pct >= 0 AND discount_pct < 1", name="ck_invline_discount"),
        sa.UniqueConstraint("invoice_id", "line_no", name="uq_inv_line_no"),
        sa.ForeignKeyConstraint(["invoice_id"], ["invoices.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["item_id"], ["items.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tax_code_id"], ["tax_codes.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_invoice_lines_tenant_id", "invoice_lines", ["tenant_id"])
    op.create_index("ix_invoice_lines_invoice_id", "invoice_lines", ["invoice_id"])

    # --- bills --------------------------------------------------------------
    op.create_table(
        "bills",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("number", sa.String(64), nullable=False),
        sa.Column("supplier_reference", sa.String(128), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("contact_id", sa.UUID(), nullable=False),
        sa.Column("issue_date", sa.String(10), nullable=False),
        sa.Column("due_date", sa.String(10), nullable=True),
        sa.Column("period_name", sa.String(7), nullable=True),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("fx_rate", sa.Numeric(19, 8), nullable=False, server_default="1"),
        sa.Column("subtotal", sa.Numeric(19, 4), nullable=False, server_default="0"),
        sa.Column("tax_total", sa.Numeric(19, 4), nullable=False, server_default="0"),
        sa.Column("total", sa.Numeric(19, 4), nullable=False, server_default="0"),
        sa.Column("amount_due", sa.Numeric(19, 4), nullable=False, server_default="0"),
        sa.Column("functional_total", sa.Numeric(19, 4), nullable=False, server_default="0"),
        sa.Column("journal_entry_id", sa.UUID(), nullable=True),
        sa.Column("approved_by", sa.UUID(), nullable=True),
        sa.Column("approved_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "status IN ('draft','awaiting_approval','approved','partial','paid','void')",
            name="ck_bills_status",
        ),
        sa.UniqueConstraint("tenant_id", "number", name="uq_bills_tenant_number"),
        sa.ForeignKeyConstraint(["contact_id"], ["contacts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["journal_entry_id"], ["journal_entries.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_bills_tenant_id", "bills", ["tenant_id"])
    op.create_index("ix_bills_contact_id", "bills", ["contact_id"])

    # --- bill_lines ---------------------------------------------------------
    op.create_table(
        "bill_lines",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("bill_id", sa.UUID(), nullable=False),
        sa.Column("line_no", sa.SmallInteger(), nullable=False),
        sa.Column("item_id", sa.UUID(), nullable=True),
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column("tax_code_id", sa.UUID(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("quantity", sa.Numeric(19, 4), nullable=False, server_default="1"),
        sa.Column("unit_price", sa.Numeric(19, 4), nullable=False, server_default="0"),
        sa.Column("discount_pct", sa.Numeric(5, 4), nullable=False, server_default="0"),
        sa.Column("line_amount", sa.Numeric(19, 4), nullable=False, server_default="0"),
        sa.Column("tax_amount", sa.Numeric(19, 4), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("quantity > 0", name="ck_billline_qty"),
        sa.CheckConstraint("discount_pct >= 0 AND discount_pct < 1", name="ck_billline_discount"),
        sa.UniqueConstraint("bill_id", "line_no", name="uq_bill_line_no"),
        sa.ForeignKeyConstraint(["bill_id"], ["bills.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["item_id"], ["items.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tax_code_id"], ["tax_codes.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_bill_lines_tenant_id", "bill_lines", ["tenant_id"])
    op.create_index("ix_bill_lines_bill_id", "bill_lines", ["bill_id"])

    # --- payments -----------------------------------------------------------
    op.create_table(
        "payments",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("number", sa.String(64), nullable=False),
        sa.Column("payment_type", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("contact_id", sa.UUID(), nullable=True),
        sa.Column("payment_date", sa.String(10), nullable=False),
        sa.Column("amount", sa.Numeric(19, 4), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("fx_rate", sa.Numeric(19, 8), nullable=False, server_default="1"),
        sa.Column("functional_amount", sa.Numeric(19, 4), nullable=False),
        sa.Column("bank_account_id", sa.UUID(), nullable=True),
        sa.Column("reference", sa.String(128), nullable=True),
        sa.Column("journal_entry_id", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("payment_type IN ('received','made')", name="ck_payments_type"),
        sa.CheckConstraint("status IN ('pending','applied','voided')", name="ck_payments_status"),
        sa.CheckConstraint("amount > 0", name="ck_payments_positive"),
        sa.UniqueConstraint("tenant_id", "number", name="uq_payments_tenant_number"),
        sa.ForeignKeyConstraint(["contact_id"], ["contacts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["bank_account_id"], ["accounts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["journal_entry_id"], ["journal_entries.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_payments_tenant_id", "payments", ["tenant_id"])
    op.create_index("ix_payments_contact_id", "payments", ["contact_id"])

    # --- payment_allocations ------------------------------------------------
    op.create_table(
        "payment_allocations",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("payment_id", sa.UUID(), nullable=False),
        sa.Column("invoice_id", sa.UUID(), nullable=True),
        sa.Column("bill_id", sa.UUID(), nullable=True),
        sa.Column("amount", sa.Numeric(19, 4), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("amount > 0", name="ck_palloc_positive"),
        sa.CheckConstraint(
            "(invoice_id IS NOT NULL AND bill_id IS NULL) OR (invoice_id IS NULL AND bill_id IS NOT NULL)",
            name="ck_palloc_exclusive",
        ),
        sa.ForeignKeyConstraint(["payment_id"], ["payments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["invoice_id"], ["invoices.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["bill_id"], ["bills.id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_payment_allocations_tenant_id", "payment_allocations", ["tenant_id"])
    op.create_index("ix_payment_allocations_payment_id", "payment_allocations", ["payment_id"])
    op.create_index("ix_payment_allocations_invoice_id", "payment_allocations", ["invoice_id"])
    op.create_index("ix_payment_allocations_bill_id", "payment_allocations", ["bill_id"])


def downgrade() -> None:
    op.drop_table("payment_allocations")
    op.drop_table("payments")
    op.drop_table("bill_lines")
    op.drop_table("bills")
    op.drop_table("invoice_lines")
    op.drop_table("invoices")
    op.drop_table("tax_codes")
    op.drop_table("items")
    op.drop_table("contacts")
