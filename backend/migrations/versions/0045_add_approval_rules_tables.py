"""feat(approval): add approval_rules and approval_delegations tables

Revision ID: 0043
Revises: 0042
Create Date: 2026-04-18

Issue #61: Configurable approval workflow engine.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0045"
down_revision: str | None = "0044"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # -- approval_rules -------------------------------------------------------
    op.create_table(
        "approval_rules",
        sa.Column("id", sa.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.UUID(as_uuid=False),
            sa.ForeignKey("tenants.id", ondelete="RESTRICT"),
            nullable=False,
            index=True,
        ),
        sa.Column("entity_type", sa.String(50), nullable=False),
        sa.Column("condition_field", sa.String(50), nullable=False),
        sa.Column("condition_operator", sa.String(10), nullable=False),
        sa.Column("condition_value", sa.Numeric(19, 4), nullable=False),
        sa.Column("required_role", sa.String(50), nullable=False),
        sa.Column("approval_order", sa.Integer, nullable=False, server_default="1"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("description", sa.Text, nullable=True),
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
        sa.Column("created_by", sa.UUID(as_uuid=False), nullable=True),
        sa.Column("updated_by", sa.UUID(as_uuid=False), nullable=True),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.CheckConstraint(
            "entity_type IN ('invoice','bill','journal','expense_claim')",
            name="ck_approval_rules_entity_type",
        ),
        sa.CheckConstraint(
            "condition_operator IN ('gte','lte','gt','lt','eq')",
            name="ck_approval_rules_operator",
        ),
        sa.CheckConstraint(
            "condition_field IN ('total','amount')",
            name="ck_approval_rules_field",
        ),
        sa.CheckConstraint("approval_order > 0", name="ck_approval_rules_order_positive"),
    )

    # -- approval_delegations -------------------------------------------------
    op.create_table(
        "approval_delegations",
        sa.Column("id", sa.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.UUID(as_uuid=False),
            sa.ForeignKey("tenants.id", ondelete="RESTRICT"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "delegator_id",
            sa.UUID(as_uuid=False),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "delegate_id",
            sa.UUID(as_uuid=False),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
            index=True,
        ),
        sa.Column("start_date", sa.Date, nullable=False),
        sa.Column("end_date", sa.Date, nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
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
        sa.Column("created_by", sa.UUID(as_uuid=False), nullable=True),
        sa.Column("updated_by", sa.UUID(as_uuid=False), nullable=True),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.CheckConstraint(
            "start_date <= end_date", name="ck_approval_delegations_date_range"
        ),
        sa.CheckConstraint(
            "delegator_id != delegate_id", name="ck_approval_delegations_no_self"
        ),
    )

    # -- RLS policies ---------------------------------------------------------
    for table in ("approval_rules", "approval_delegations"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation ON {table} "
            f"USING (tenant_id = current_setting('app.tenant_id')::uuid)"
        )


def downgrade() -> None:
    for table in ("approval_delegations", "approval_rules"):
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
    op.drop_table("approval_delegations")
    op.drop_table("approval_rules")
