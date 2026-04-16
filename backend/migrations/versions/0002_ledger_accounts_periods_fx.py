"""ledger: accounts periods fx_rates

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-14
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── Accounts (Chart of Accounts) ─────────────────────────────────────────
    op.create_table(
        "accounts",
        sa.Column("id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("code", sa.String(20), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("type", sa.String(16), nullable=False),
        sa.Column("subtype", sa.String(32), nullable=False),
        sa.Column("normal_balance", sa.String(6), nullable=False),
        sa.Column("parent_id", sa.UUID(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("currency", sa.String(3), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("reporting_tags", sa.ARRAY(sa.Text()), nullable=False, server_default="{}"),
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
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["parent_id"], ["accounts.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("tenant_id", "code", name="uq_accounts_tenant_code"),
        sa.CheckConstraint(
            "type IN ('asset','liability','equity','revenue','expense')", name="ck_accounts_type"
        ),
        sa.CheckConstraint(
            "normal_balance IN ('debit','credit')", name="ck_accounts_normal_balance"
        ),
    )
    op.create_index("ix_accounts_tenant_id", "accounts", ["tenant_id"])
    op.create_index("ix_accounts_parent_id", "accounts", ["parent_id"])

    # Row-Level Security
    op.execute("ALTER TABLE accounts ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY tenant_isolation ON accounts
        USING (tenant_id = current_setting('app.tenant_id', true)::uuid)
    """)

    # ── Periods ───────────────────────────────────────────────────────────────
    op.create_table(
        "periods",
        sa.Column("id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(20), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="open"),
        sa.Column("closed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("closed_by", sa.UUID(), nullable=True),
        sa.Column("closed_reason", sa.Text(), nullable=True),
        sa.Column("reopened_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("reopened_by", sa.UUID(), nullable=True),
        sa.Column("reopened_reason", sa.Text(), nullable=True),
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
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("tenant_id", "name", name="uq_periods_tenant_name"),
        sa.CheckConstraint(
            "status IN ('open','soft_closed','hard_closed','audited')", name="ck_periods_status"
        ),
        sa.CheckConstraint("start_date <= end_date", name="ck_periods_dates"),
    )
    op.create_index("ix_periods_tenant_id", "periods", ["tenant_id"])
    op.create_index("ix_periods_start_date", "periods", ["tenant_id", "start_date"])

    op.execute("ALTER TABLE periods ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY tenant_isolation ON periods
        USING (tenant_id = current_setting('app.tenant_id', true)::uuid)
    """)

    # ── FX rates ──────────────────────────────────────────────────────────────
    op.create_table(
        "fx_rates",
        sa.Column("id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("from_currency", sa.String(3), nullable=False),
        sa.Column("to_currency", sa.String(3), nullable=False),
        sa.Column("rate_date", sa.Date(), nullable=False),
        sa.Column("rate", sa.Numeric(19, 8), nullable=False),
        sa.Column("source", sa.String(64), nullable=False, server_default="manual"),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "from_currency", "to_currency", "rate_date", name="uq_fx_rates_pair_date"
        ),
        sa.CheckConstraint("rate > 0", name="ck_fx_rates_positive"),
    )
    op.create_index(
        "ix_fx_rates_pair_date", "fx_rates", ["from_currency", "to_currency", "rate_date"]
    )


def downgrade() -> None:
    op.drop_table("fx_rates")
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON periods")
    op.drop_table("periods")
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON accounts")
    op.drop_table("accounts")
