"""bank-feeds: add bank_feed_connections table and institution_transaction_id column

Revision ID: 0036
Revises: 0035
Create Date: 2026-04-18
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0037"
down_revision: str | None = "0036"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # -- New table: bank_feed_connections -----------------------------------
    op.create_table(
        "bank_feed_connections",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.dialects.postgresql.UUID(as_uuid=False),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "bank_account_id",
            sa.dialects.postgresql.UUID(as_uuid=False),
            sa.ForeignKey("bank_accounts.id", ondelete="RESTRICT"),
            nullable=False,
            index=True,
        ),
        sa.Column("provider", sa.String(50), nullable=False, server_default="plaid"),
        sa.Column("access_token_encrypted", sa.Text, nullable=True),
        sa.Column("item_id", sa.String(100), nullable=True),
        sa.Column("institution_id", sa.String(100), nullable=True),
        sa.Column("institution_name", sa.String(200), nullable=True),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="connected",
        ),
        sa.Column("last_sync_at", sa.dialects.postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("last_sync_cursor", sa.String(500), nullable=True),
        sa.Column("last_error", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.dialects.postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.dialects.postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("created_by", sa.dialects.postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("updated_by", sa.dialects.postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.CheckConstraint(
            "status IN ('connected','error','expired','disconnected')",
            name="ck_bank_feed_connections_status",
        ),
    )

    # -- RLS on new table --------------------------------------------------
    op.execute("ALTER TABLE bank_feed_connections ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE bank_feed_connections FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY tenant_isolation ON bank_feed_connections
        USING (tenant_id = current_setting('app.tenant_id', true)::uuid)
    """)

    # -- Add institution_transaction_id to bank_transactions ---------------
    op.add_column(
        "bank_transactions",
        sa.Column(
            "institution_transaction_id",
            sa.String(200),
            nullable=True,
            comment="External transaction ID from bank feed provider",
        ),
    )


def downgrade() -> None:
    # -- Remove institution_transaction_id from bank_transactions ----------
    op.drop_column("bank_transactions", "institution_transaction_id")

    # -- Drop RLS on bank_feed_connections ---------------------------------
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON bank_feed_connections")
    op.execute("ALTER TABLE bank_feed_connections NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE bank_feed_connections DISABLE ROW LEVEL SECURITY")

    # -- Drop table --------------------------------------------------------
    op.drop_table("bank_feed_connections")
