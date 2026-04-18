"""mobile_sync: fix client_op_id uniqueness to per-tenant scope

Drops the global unique constraint on client_op_id and replaces it with
a composite unique constraint on (tenant_id, client_op_id).

Revision ID: 0038
Revises: 0037
Create Date: 2026-04-18
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0038"
down_revision: str | None = "0037"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("uq_sync_ops_client_op_id", "sync_ops", type_="unique")
    op.create_unique_constraint(
        "uq_sync_ops_tenant_client_op",
        "sync_ops",
        ["tenant_id", "client_op_id"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_sync_ops_tenant_client_op", "sync_ops", type_="unique")
    op.create_unique_constraint(
        "uq_sync_ops_client_op_id",
        "sync_ops",
        ["client_op_id"],
    )
