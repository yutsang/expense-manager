"""ai: add ai_drafts table for persisted tool-use drafts

Replaces the process-local in-memory draft dict so proposals survive restarts
and can be audited / cleaned up by a worker.

Revision ID: 0049
Revises: 0048
Create Date: 2026-04-20
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0049"
down_revision: str | None = "0048"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_drafts",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "tenant_id",
            sa.UUID(),
            sa.ForeignKey("tenants.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "conversation_id",
            sa.UUID(),
            sa.ForeignKey("ai_conversations.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("tool_name", sa.String(100), nullable=False),
        sa.Column("payload", JSONB(), nullable=False),
        sa.Column("confirmed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("confirmed_by", sa.UUID(), nullable=True),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ai_drafts_tenant_id", "ai_drafts", ["tenant_id"])
    op.create_index("ix_ai_drafts_expires_at", "ai_drafts", ["expires_at"])

    # RLS
    op.execute("ALTER TABLE ai_drafts ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON ai_drafts "
        "USING (tenant_id = current_setting('app.tenant_id')::uuid)"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON ai_drafts")
    op.execute("ALTER TABLE ai_drafts DISABLE ROW LEVEL SECURITY")
    op.drop_index("ix_ai_drafts_expires_at", table_name="ai_drafts")
    op.drop_index("ix_ai_drafts_tenant_id", table_name="ai_drafts")
    op.drop_table("ai_drafts")
