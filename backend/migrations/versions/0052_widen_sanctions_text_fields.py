"""sanctions: widen ref_id + primary_name to TEXT (no length cap)

After 0051 widened ref_id to VARCHAR(500), prod hit ``primary_name`` next
on 2026-04-25 04:55: OpenSanctions has a handful of entries where the
primary name is a long citation/legal-reference string exceeding 500
chars (e.g. comma-joined alias bundles or "X" / "Y" disambiguators).
Rather than chase column widths, switch both fields to TEXT — Postgres
stores VARCHAR(n) and TEXT identically except for the length check, and
no length cap is the right semantic for free-form names from external
feeds.

Revision ID: 0052
Revises: 0051
Create Date: 2026-04-25
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0052"
down_revision: str | None = "0051"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "sanctions_list_entries",
        "ref_id",
        existing_type=sa.String(length=500),
        type_=sa.Text(),
        existing_nullable=False,
    )
    op.alter_column(
        "sanctions_list_entries",
        "primary_name",
        existing_type=sa.String(length=500),
        type_=sa.Text(),
        existing_nullable=False,
    )


def downgrade() -> None:
    # Will fail if any existing row exceeds the old caps — the expected
    # behaviour. Delete OpenSanctions rows before downgrading.
    op.alter_column(
        "sanctions_list_entries",
        "primary_name",
        existing_type=sa.Text(),
        type_=sa.String(length=500),
        existing_nullable=False,
    )
    op.alter_column(
        "sanctions_list_entries",
        "ref_id",
        existing_type=sa.Text(),
        type_=sa.String(length=500),
        existing_nullable=False,
    )
