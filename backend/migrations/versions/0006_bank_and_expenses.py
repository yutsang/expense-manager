"""bank_and_expenses: bank accounts, bank transactions, bank reconciliations, expense claims

Revision ID: 0006
Revises: 0005
Create Date: 2026-04-15
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- bank_accounts ----------------------------------------------------------
    op.create_table(
        "bank_accounts",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("bank_name", sa.String(255), nullable=True),
        sa.Column("account_number", sa.String(100), nullable=True),
        sa.Column("currency", sa.String(3), nullable=False, server_default="USD"),
        sa.Column("coa_account_id", sa.UUID(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("last_reconciled_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("last_reconciled_balance", sa.Numeric(19, 4), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["coa_account_id"], ["accounts.id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_bank_accounts_tenant_id", "bank_accounts", ["tenant_id"])

    # --- bank_transactions ------------------------------------------------------
    op.create_table(
        "bank_transactions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("bank_account_id", sa.UUID(), nullable=False),
        sa.Column("transaction_date", sa.Date(), nullable=False),
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column("reference", sa.String(200), nullable=True),
        sa.Column("amount", sa.Numeric(19, 4), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("is_reconciled", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("reconciled_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("journal_line_id", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["bank_account_id"], ["bank_accounts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["journal_line_id"], ["journal_lines.id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_bank_transactions_tenant_id", "bank_transactions", ["tenant_id"])
    op.create_index(
        "ix_bank_transactions_account_date",
        "bank_transactions",
        ["tenant_id", "bank_account_id", "transaction_date"],
    )

    # --- bank_reconciliations ---------------------------------------------------
    op.create_table(
        "bank_reconciliations",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("bank_account_id", sa.UUID(), nullable=False),
        sa.Column("period_id", sa.UUID(), nullable=True),
        sa.Column("statement_closing_balance", sa.Numeric(19, 4), nullable=False),
        sa.Column("book_balance", sa.Numeric(19, 4), nullable=False),
        sa.Column("difference", sa.Numeric(19, 4), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="in_progress"),
        sa.Column("reconciled_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("reconciled_by", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "status IN ('in_progress','completed')",
            name="ck_bank_recon_status",
        ),
        sa.ForeignKeyConstraint(["bank_account_id"], ["bank_accounts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["period_id"], ["periods.id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_bank_reconciliations_tenant_id", "bank_reconciliations", ["tenant_id"])
    op.create_index("ix_bank_reconciliations_account_id", "bank_reconciliations", ["bank_account_id"])

    # --- expense_claims ---------------------------------------------------------
    op.create_table(
        "expense_claims",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("number", sa.String(20), nullable=False),
        sa.Column("contact_id", sa.UUID(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("claim_date", sa.Date(), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("currency", sa.String(3), nullable=False, server_default="USD"),
        sa.Column("total_amount", sa.Numeric(19, 4), nullable=False, server_default="0"),
        sa.Column("tax_total", sa.Numeric(19, 4), nullable=False, server_default="0"),
        sa.Column("journal_entry_id", sa.UUID(), nullable=True),
        sa.Column("approved_by", sa.UUID(), nullable=True),
        sa.Column("approved_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("paid_by", sa.UUID(), nullable=True),
        sa.Column("paid_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "status IN ('draft','submitted','approved','rejected','paid')",
            name="ck_expense_claims_status",
        ),
        sa.UniqueConstraint("tenant_id", "number", name="uq_expense_claims_tenant_number"),
        sa.ForeignKeyConstraint(["contact_id"], ["contacts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["journal_entry_id"], ["journal_entries.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_expense_claims_tenant_id", "expense_claims", ["tenant_id"])
    op.create_index("ix_expense_claims_contact_id", "expense_claims", ["contact_id"])

    # --- expense_claim_lines ----------------------------------------------------
    op.create_table(
        "expense_claim_lines",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("claim_id", sa.UUID(), nullable=False),
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column("tax_code_id", sa.UUID(), nullable=True),
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column("amount", sa.Numeric(19, 4), nullable=False),
        sa.Column("tax_amount", sa.Numeric(19, 4), nullable=False, server_default="0"),
        sa.Column("receipt_url", sa.String(1000), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["claim_id"], ["expense_claims.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tax_code_id"], ["tax_codes.id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_expense_claim_lines_tenant_id", "expense_claim_lines", ["tenant_id"])
    op.create_index("ix_expense_claim_lines_claim_id", "expense_claim_lines", ["claim_id"])

    # --- RLS policies -----------------------------------------------------------
    _NEW_TABLES = [
        "bank_accounts",
        "bank_transactions",
        "bank_reconciliations",
        "expense_claims",
        "expense_claim_lines",
    ]
    for table in _NEW_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(f"""
            CREATE POLICY tenant_isolation ON {table}
            USING (tenant_id = current_setting('app.tenant_id', true)::uuid)
        """)


def downgrade() -> None:
    _NEW_TABLES = [
        "bank_accounts",
        "bank_transactions",
        "bank_reconciliations",
        "expense_claims",
        "expense_claim_lines",
    ]
    for table in reversed(_NEW_TABLES):
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")

    op.drop_table("expense_claim_lines")
    op.drop_table("expense_claims")
    op.drop_table("bank_reconciliations")
    op.drop_table("bank_transactions")
    op.drop_table("bank_accounts")
