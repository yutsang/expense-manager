"""sanctions: add search_text column + GIN trgm index for fast name search

The existing GIN index on the ``aliases`` JSONB column (created in 0011)
only supports containment operators (``@>``, ``?``, ``?|``, ``?&``). It
does **not** accelerate ILIKE on individual alias names, so the previous
search query — ``EXISTS (SELECT 1 FROM jsonb_array_elements(aliases)
WHERE a->>'name' ILIKE :pat)`` — does a full scan and explodes at 280k+
entries (observed 2026-04-26: search latency in seconds).

Add a denormalised ``search_text`` column populated by the application
on insert (lowercased ``primary_name`` + ``aliases[*].name`` +
``countries`` + ``programs``, space-joined). Index it with GIN trigrams
so ILIKE ``%tok%`` is index-scan fast even for unanchored queries.

Existing rows are left with NULL — search will skip them. After deploy,
re-trigger the sanctions refresh and the new active snapshot will have
search_text populated. The previous snapshot is marked is_active=False
and excluded from queries, so users don't see stale empty results.

Revision ID: 0053
Revises: 0052
Create Date: 2026-04-26
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0053"
down_revision: str | None = "0052"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "sanctions_list_entries",
        sa.Column("search_text", sa.Text(), nullable=True),
    )
    # pg_trgm extension is already enabled by 0011 for ix_sanctions_entries_name_trgm.
    op.execute(
        "CREATE INDEX ix_sanctions_entries_search_text_trgm "
        "ON sanctions_list_entries USING GIN (search_text gin_trgm_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_sanctions_entries_search_text_trgm")
    op.drop_column("sanctions_list_entries", "search_text")
