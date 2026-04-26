"""sanctions: capture entity period (first_seen, last_seen, last_change) + datasets

Each OpenSanctions entity carries timestamps for when it was first seen,
last seen, and last changed in upstream sources, plus a ``datasets`` list
naming the upstream sanctioning authorities (e.g. ``us_ofac_sdn``,
``eu_fsf``). The detail page wants to show "active since" / "last
updated" and "sanctioned by …", but the existing schema stored none of
this — they were silently dropped by the parser.

Add four nullable columns: three timestamptz for the period, one JSONB
for the datasets list. Backfilled on the next refresh; pre-existing rows
will keep NULL and the UI shows "—".

Revision ID: 0054
Revises: 0053
Create Date: 2026-04-26
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "0054"
down_revision: str | None = "0053"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "sanctions_list_entries",
        sa.Column("first_seen", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.add_column(
        "sanctions_list_entries",
        sa.Column("last_seen", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.add_column(
        "sanctions_list_entries",
        sa.Column("last_change", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.add_column(
        "sanctions_list_entries",
        sa.Column("datasets", pg.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("sanctions_list_entries", "datasets")
    op.drop_column("sanctions_list_entries", "last_change")
    op.drop_column("sanctions_list_entries", "last_seen")
    op.drop_column("sanctions_list_entries", "first_seen")
