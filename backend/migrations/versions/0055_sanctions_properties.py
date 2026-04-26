"""sanctions: capture full FtM properties (address, IDs, dates, position, etc.)

The detail page wants to show address, ID/passport numbers, birth
date+place, position/title, nationality, and source URLs — none of
which we were storing. OpenSanctions ships these in
``data.properties`` per FtM entity, but the parser only extracted name,
alias, country, topics, and notes. Add a single JSONB ``properties``
column that holds the dict of additional fields the parser cares about,
and let the UI pick what it wants to render.

Storing as a single JSONB blob (vs adding 8+ typed columns) is
deliberate: OpenSanctions has dozens of FtM property names, ~10 are
useful for UI today, and what we want to render is likely to evolve.

Revision ID: 0055
Revises: 0054
Create Date: 2026-04-27
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "0055"
down_revision: str | None = "0054"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "sanctions_list_entries",
        sa.Column("properties", pg.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("sanctions_list_entries", "properties")
