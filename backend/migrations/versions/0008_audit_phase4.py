"""audit_phase4: audit_chain_verifications + report_snapshots

Revision ID: 0008
Revises: 0007
Create Date: 2026-04-16
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- audit_chain_verifications -----------------------------------------------
    op.create_table(
        "audit_chain_verifications",
        sa.Column("id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("verified_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("chain_length", sa.Integer(), nullable=False),
        sa.Column("last_event_id", sa.UUID(), nullable=True),
        sa.Column("is_valid", sa.Boolean(), nullable=False),
        sa.Column("break_at_event_id", sa.UUID(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_audit_chain_verif_tenant", "audit_chain_verifications", ["tenant_id", "verified_at"]
    )

    # --- report_snapshots --------------------------------------------------------
    op.create_table(
        "report_snapshots",
        sa.Column("id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("report_type", sa.String(50), nullable=False),
        sa.Column("params", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("generated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_report_snapshots_tenant", "report_snapshots", ["tenant_id", "generated_at"])

    # --- RLS policies -----------------------------------------------------------
    _NEW_TABLES = ["audit_chain_verifications", "report_snapshots"]
    for table in _NEW_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(f"""
            CREATE POLICY tenant_isolation ON {table}
            USING (tenant_id = current_setting('app.tenant_id', true)::uuid)
        """)


def downgrade() -> None:
    _NEW_TABLES = ["audit_chain_verifications", "report_snapshots"]
    for table in reversed(_NEW_TABLES):
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")

    op.drop_table("report_snapshots")
    op.drop_table("audit_chain_verifications")
