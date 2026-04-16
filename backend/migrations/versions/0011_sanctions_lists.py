"""sanctions: sanctions_list_snapshots, sanctions_list_entries, contact_sanctions_results

Revision ID: 0011
Revises: 0010
Create Date: 2026-04-16
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── sanctions_list_snapshots ──────────────────────────────────────────────
    op.create_table(
        "sanctions_list_snapshots",
        sa.Column("id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("fetched_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("entry_count", sa.Integer(), nullable=False),
        sa.Column("sha256_hash", sa.String(64), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sanctions_snapshots_source", "sanctions_list_snapshots", ["source"])

    # ── sanctions_list_entries ────────────────────────────────────────────────
    op.create_table(
        "sanctions_list_entries",
        sa.Column("id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("snapshot_id", sa.UUID(), nullable=False),
        sa.Column("ref_id", sa.String(100), nullable=False),
        sa.Column("entity_type", sa.String(20), nullable=False),
        sa.Column("primary_name", sa.String(500), nullable=False),
        sa.Column("aliases", JSONB(), nullable=False, server_default="'[]'"),
        sa.Column("countries", JSONB(), nullable=False, server_default="'[]'"),
        sa.Column("programs", JSONB(), nullable=False, server_default="'[]'"),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.Column("source", sa.String(50), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["snapshot_id"], ["sanctions_list_snapshots.id"], ondelete="CASCADE"
        ),
    )
    op.create_index("ix_sanctions_entries_snapshot", "sanctions_list_entries", ["snapshot_id"])
    op.create_index("ix_sanctions_entries_ref_id", "sanctions_list_entries", ["ref_id"])
    op.execute(
        "CREATE INDEX ix_sanctions_entries_aliases ON sanctions_list_entries USING GIN (aliases)"
    )

    # ── contact_sanctions_results ─────────────────────────────────────────────
    op.create_table(
        "contact_sanctions_results",
        sa.Column("id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("contact_id", sa.UUID(), nullable=False),
        sa.Column("screened_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("snapshot_id", sa.UUID(), nullable=True),
        sa.Column("match_status", sa.String(20), nullable=False, server_default="'clear'"),
        sa.Column("match_score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("matched_entry_id", sa.UUID(), nullable=True),
        sa.Column("matched_name", sa.String(500), nullable=True),
        sa.Column("details", JSONB(), nullable=False, server_default="'[]'"),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["contact_id"], ["contacts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["snapshot_id"], ["sanctions_list_snapshots.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["matched_entry_id"], ["sanctions_list_entries.id"], ondelete="SET NULL"
        ),
        sa.UniqueConstraint("tenant_id", "contact_id", name="uq_sanctions_results_tenant_contact"),
    )
    op.create_index("ix_sanctions_results_tenant", "contact_sanctions_results", ["tenant_id"])
    op.create_index("ix_sanctions_results_contact", "contact_sanctions_results", ["contact_id"])

    # RLS on contact_sanctions_results only (snapshots/entries are global reference data)
    op.execute("ALTER TABLE contact_sanctions_results ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE contact_sanctions_results FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY contact_sanctions_results_tenant ON contact_sanctions_results
        USING (tenant_id = current_setting('app.tenant_id', true)::uuid)
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS contact_sanctions_results_tenant ON contact_sanctions_results")
    op.execute("ALTER TABLE contact_sanctions_results NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE contact_sanctions_results DISABLE ROW LEVEL SECURITY")
    op.drop_table("contact_sanctions_results")
    op.drop_index("ix_sanctions_entries_aliases", table_name="sanctions_list_entries")
    op.drop_index("ix_sanctions_entries_ref_id", table_name="sanctions_list_entries")
    op.drop_index("ix_sanctions_entries_snapshot", table_name="sanctions_list_entries")
    op.drop_table("sanctions_list_entries")
    op.drop_index("ix_sanctions_snapshots_source", table_name="sanctions_list_snapshots")
    op.drop_table("sanctions_list_snapshots")
