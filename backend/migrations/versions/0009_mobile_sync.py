"""mobile_sync: sync_devices + sync_ops tables

Revision ID: 0009
Revises: 0008
Create Date: 2026-04-16
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- sync_devices ------------------------------------------------------------
    op.create_table(
        "sync_devices",
        sa.Column("id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("device_fingerprint", sa.String(128), nullable=False),
        sa.Column(
            "platform",
            sa.String(10),
            nullable=False,
            server_default="web",
        ),
        sa.Column("app_version", sa.String(20), nullable=True),
        sa.Column("push_token", sa.Text(), nullable=True),
        sa.Column("last_seen", sa.TIMESTAMP(timezone=True), nullable=True),
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "device_fingerprint", name="uq_sync_devices_tenant_fp"),
        sa.CheckConstraint(
            "platform IN ('ios','android','web')",
            name="ck_sync_devices_platform",
        ),
    )
    op.create_index("ix_sync_devices_tenant", "sync_devices", ["tenant_id"])
    op.create_index("ix_sync_devices_user", "sync_devices", ["tenant_id", "user_id"])

    # --- sync_ops ----------------------------------------------------------------
    op.create_table(
        "sync_ops",
        sa.Column("id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("client_op_id", sa.String(128), nullable=False),
        sa.Column("device_id", sa.UUID(), nullable=True),
        sa.Column("entity_type", sa.String(50), nullable=True),
        sa.Column("entity_id", sa.UUID(), nullable=True),
        sa.Column("base_version", sa.Integer(), nullable=True),
        sa.Column("applied_version", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("applied_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("client_op_id", name="uq_sync_ops_client_op_id"),
        sa.ForeignKeyConstraint(["device_id"], ["sync_devices.id"], ondelete="SET NULL"),
        sa.CheckConstraint(
            "status IN ('applied','conflict','error')",
            name="ck_sync_ops_status",
        ),
    )
    op.create_index("ix_sync_ops_tenant", "sync_ops", ["tenant_id"])
    op.create_index("ix_sync_ops_device", "sync_ops", ["device_id"])

    # --- RLS policies -----------------------------------------------------------
    _NEW_TABLES = ["sync_devices", "sync_ops"]
    for table in _NEW_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(f"""
            CREATE POLICY tenant_isolation ON {table}
            USING (tenant_id = current_setting('app.tenant_id', true)::uuid)
            """)


def downgrade() -> None:
    _NEW_TABLES = ["sync_devices", "sync_ops"]
    for table in reversed(_NEW_TABLES):
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")

    op.drop_table("sync_ops")
    op.drop_table("sync_devices")
