"""schema: add missing audit columns on 8 tables

Revision ID: 0042
Revises: 0041
Create Date: 2026-04-18

Adds missing created_at, updated_at, created_by, updated_by columns to:
  - expense_claim_lines (all four)
  - sessions (updated_at, created_by, updated_by)
  - sync_ops (updated_at, created_by, updated_by)
  - sanctions_list_snapshots (all four)
  - sanctions_list_entries (all four)
  - contact_sanctions_results (all four)
  - attachments (updated_at, created_by, updated_by)
  - report_snapshots (updated_at, updated_by)
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op

revision: str = "0044"
down_revision: str | None = "0043"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# (table, column_name, column_type, nullable, server_default)
_COLUMNS: list[tuple[str, str, Any, bool, str | None]] = [
    # expense_claim_lines
    ("expense_claim_lines", "created_at", sa.TIMESTAMP(timezone=True), False, "now()"),
    ("expense_claim_lines", "updated_at", sa.TIMESTAMP(timezone=True), False, "now()"),
    ("expense_claim_lines", "created_by", sa.UUID(), True, None),
    ("expense_claim_lines", "updated_by", sa.UUID(), True, None),
    # sessions
    ("sessions", "updated_at", sa.TIMESTAMP(timezone=True), False, "now()"),
    ("sessions", "created_by", sa.UUID(), True, None),
    ("sessions", "updated_by", sa.UUID(), True, None),
    # sync_ops
    ("sync_ops", "updated_at", sa.TIMESTAMP(timezone=True), False, "now()"),
    ("sync_ops", "created_by", sa.UUID(), True, None),
    ("sync_ops", "updated_by", sa.UUID(), True, None),
    # sanctions_list_snapshots
    ("sanctions_list_snapshots", "created_at", sa.TIMESTAMP(timezone=True), False, "now()"),
    ("sanctions_list_snapshots", "updated_at", sa.TIMESTAMP(timezone=True), False, "now()"),
    ("sanctions_list_snapshots", "created_by", sa.UUID(), True, None),
    ("sanctions_list_snapshots", "updated_by", sa.UUID(), True, None),
    # sanctions_list_entries
    ("sanctions_list_entries", "created_at", sa.TIMESTAMP(timezone=True), False, "now()"),
    ("sanctions_list_entries", "updated_at", sa.TIMESTAMP(timezone=True), False, "now()"),
    ("sanctions_list_entries", "created_by", sa.UUID(), True, None),
    ("sanctions_list_entries", "updated_by", sa.UUID(), True, None),
    # contact_sanctions_results
    ("contact_sanctions_results", "created_at", sa.TIMESTAMP(timezone=True), False, "now()"),
    ("contact_sanctions_results", "updated_at", sa.TIMESTAMP(timezone=True), False, "now()"),
    ("contact_sanctions_results", "created_by", sa.UUID(), True, None),
    ("contact_sanctions_results", "updated_by", sa.UUID(), True, None),
    # attachments
    ("attachments", "updated_at", sa.TIMESTAMP(timezone=True), False, "now()"),
    ("attachments", "created_by", sa.UUID(), True, None),
    ("attachments", "updated_by", sa.UUID(), True, None),
    # report_snapshots
    ("report_snapshots", "updated_at", sa.TIMESTAMP(timezone=True), False, "now()"),
    ("report_snapshots", "updated_by", sa.UUID(), True, None),
]


def upgrade() -> None:
    for table, col_name, col_type, nullable, server_default in _COLUMNS:
        op.add_column(
            table,
            sa.Column(
                col_name,
                col_type,
                nullable=nullable,
                server_default=sa.text(server_default) if server_default else None,
            ),
        )


def downgrade() -> None:
    for table, col_name, _col_type, _nullable, _server_default in reversed(_COLUMNS):
        op.drop_column(table, col_name)
