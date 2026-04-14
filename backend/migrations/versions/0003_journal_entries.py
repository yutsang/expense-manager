"""ledger: journal_entries journal_lines balance_trigger

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-14
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── Journal entries ───────────────────────────────────────────────────────
    op.create_table(
        "journal_entries",
        sa.Column("id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("number", sa.String(32), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("period_id", sa.UUID(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("source_type", sa.String(32), nullable=False, server_default="manual"),
        sa.Column("source_id", sa.UUID(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
        sa.Column("void_of", sa.UUID(), nullable=True),
        sa.Column("fx_rate_date", sa.Date(), nullable=True),
        sa.Column("total_debit", sa.Numeric(19, 4), nullable=False, server_default="0"),
        sa.Column("total_credit", sa.Numeric(19, 4), nullable=False, server_default="0"),
        sa.Column("currency", sa.String(3), nullable=False, server_default="USD"),
        sa.Column("posted_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("posted_by", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["period_id"], ["periods.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["void_of"], ["journal_entries.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("tenant_id", "number", name="uq_je_tenant_number"),
        sa.CheckConstraint(
            "status IN ('draft','posted','void')", name="ck_je_status"
        ),
        sa.CheckConstraint(
            "source_type IN ('manual','invoice','bill','payment','bank','fx_reval','period_close','ai_draft')",
            name="ck_je_source_type",
        ),
    )
    op.create_index("ix_je_tenant_id", "journal_entries", ["tenant_id"])
    op.create_index("ix_je_period_id", "journal_entries", ["period_id"])
    op.create_index("ix_je_date", "journal_entries", ["tenant_id", "date"])
    op.create_index("ix_je_status", "journal_entries", ["tenant_id", "status"])

    op.execute("ALTER TABLE journal_entries ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY tenant_isolation ON journal_entries
        USING (tenant_id = current_setting('app.tenant_id', true)::uuid)
    """)

    # ── Journal lines ─────────────────────────────────────────────────────────
    op.create_table(
        "journal_lines",
        sa.Column("id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("journal_entry_id", sa.UUID(), nullable=False),
        sa.Column("line_no", sa.SmallInteger(), nullable=False),
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column("contact_id", sa.UUID(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("debit", sa.Numeric(19, 4), nullable=False, server_default="0"),
        sa.Column("credit", sa.Numeric(19, 4), nullable=False, server_default="0"),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("fx_rate", sa.Numeric(19, 8), nullable=True),
        sa.Column("functional_debit", sa.Numeric(19, 4), nullable=False, server_default="0"),
        sa.Column("functional_credit", sa.Numeric(19, 4), nullable=False, server_default="0"),
        sa.Column("tracking", sa.JSON(), nullable=False, server_default="{}"),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["journal_entry_id"], ["journal_entries.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("journal_entry_id", "line_no", name="uq_jl_entry_line"),
        sa.CheckConstraint("debit >= 0 AND credit >= 0", name="ck_jl_non_negative"),
        sa.CheckConstraint(
            "(debit > 0 AND credit = 0) OR (credit > 0 AND debit = 0) OR (debit = 0 AND credit = 0)",
            name="ck_jl_one_side",
        ),
    )
    op.create_index("ix_jl_journal_entry_id", "journal_lines", ["journal_entry_id"])
    op.create_index("ix_jl_account_id", "journal_lines", ["account_id"])
    op.create_index("ix_jl_tenant_id", "journal_lines", ["tenant_id"])

    op.execute("ALTER TABLE journal_lines ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY tenant_isolation ON journal_lines
        USING (tenant_id = current_setting('app.tenant_id', true)::uuid)
    """)

    # ── Balance trigger: sum(functional_debit) = sum(functional_credit) on post ──
    op.execute("""
        CREATE OR REPLACE FUNCTION check_journal_balance()
        RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE
            v_debit  NUMERIC;
            v_credit NUMERIC;
        BEGIN
            -- Only enforce on status transition to 'posted'
            IF NEW.status = 'posted' AND (OLD.status IS DISTINCT FROM 'posted') THEN
                SELECT COALESCE(SUM(functional_debit), 0),
                       COALESCE(SUM(functional_credit), 0)
                INTO v_debit, v_credit
                FROM journal_lines
                WHERE journal_entry_id = NEW.id;

                IF v_debit <> v_credit THEN
                    RAISE EXCEPTION
                        'Journal entry % is unbalanced: debit=% credit=%',
                        NEW.id, v_debit, v_credit;
                END IF;
                IF v_debit = 0 THEN
                    RAISE EXCEPTION
                        'Journal entry % has no lines', NEW.id;
                END IF;
            END IF;
            RETURN NEW;
        END;
        $$;
    """)
    op.execute("""
        CREATE TRIGGER trg_check_journal_balance
        BEFORE UPDATE ON journal_entries
        FOR EACH ROW EXECUTE FUNCTION check_journal_balance();
    """)

    # ── JE number sequence function ───────────────────────────────────────────
    op.execute("""
        CREATE OR REPLACE FUNCTION next_je_number(p_tenant_id UUID, p_year INT)
        RETURNS TEXT LANGUAGE plpgsql AS $$
        DECLARE
            v_seq INT;
        BEGIN
            SELECT COALESCE(MAX(
                CAST(SPLIT_PART(number, '-', 2) AS INT)
            ), 0) + 1
            INTO v_seq
            FROM journal_entries
            WHERE tenant_id = p_tenant_id
              AND number LIKE (p_year::TEXT || '-%');

            RETURN p_year::TEXT || '-' || LPAD(v_seq::TEXT, 5, '0');
        END;
        $$;
    """)


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS next_je_number(UUID, INT)")
    op.execute("DROP TRIGGER IF EXISTS trg_check_journal_balance ON journal_entries")
    op.execute("DROP FUNCTION IF EXISTS check_journal_balance()")
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON journal_lines")
    op.drop_table("journal_lines")
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON journal_entries")
    op.drop_table("journal_entries")
