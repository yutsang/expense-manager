"""fx: add rate_timestamp/bid/ask; consolidation: entity_groups + members

Revision ID: 0020
Revises: 0019
Create Date: 2026-04-18
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID

revision: str = "0020"
down_revision: str | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── Feature #69: FX rate intra-day columns ──
    op.add_column(
        "fx_rates",
        sa.Column("rate_timestamp", TIMESTAMP(timezone=True), nullable=True),
    )
    op.add_column(
        "fx_rates",
        sa.Column("bid_rate", sa.Numeric(19, 8), nullable=True),
    )
    op.add_column(
        "fx_rates",
        sa.Column("ask_rate", sa.Numeric(19, 8), nullable=True),
    )

    # ── Feature #71: Multi-entity consolidation ──
    op.create_table(
        "entity_groups",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "parent_tenant_id",
            UUID(as_uuid=False),
            sa.ForeignKey("tenants.id", ondelete="RESTRICT"),
            nullable=False,
            index=True,
        ),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("created_at", TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("created_by", UUID(as_uuid=False), nullable=True),
        sa.Column("updated_by", UUID(as_uuid=False), nullable=True),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
    )

    op.create_table(
        "entity_group_members",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "group_id",
            UUID(as_uuid=False),
            sa.ForeignKey("entity_groups.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "member_tenant_id",
            UUID(as_uuid=False),
            sa.ForeignKey("tenants.id", ondelete="RESTRICT"),
            nullable=False,
            index=True,
        ),
        sa.Column("ownership_pct", sa.Numeric(5, 2), nullable=False, server_default="100"),
        sa.Column("created_at", TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("created_by", UUID(as_uuid=False), nullable=True),
        sa.Column("updated_by", UUID(as_uuid=False), nullable=True),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.UniqueConstraint("group_id", "member_tenant_id", name="uq_entity_group_members_group_tenant"),
        sa.CheckConstraint(
            "ownership_pct > 0 AND ownership_pct <= 100",
            name="ck_entity_group_members_ownership_pct",
        ),
    )


def downgrade() -> None:
    op.drop_table("entity_group_members")
    op.drop_table("entity_groups")
    op.drop_column("fx_rates", "ask_rate")
    op.drop_column("fx_rates", "bid_rate")
    op.drop_column("fx_rates", "rate_timestamp")
