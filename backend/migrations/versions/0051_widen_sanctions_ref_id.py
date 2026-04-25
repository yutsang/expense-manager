"""sanctions: widen sanctions_list_entries.ref_id from VARCHAR(100) to VARCHAR(500)

The OpenSanctions Default feed uses compound identifiers that include the
slugified entity name (e.g. ``ch-finmawa-capstone-investment-banking-ltd``).
Some entries — especially long corporate names with subsidiary suffixes —
exceed 100 characters, causing ``StringDataRightTruncationError`` on the
prod refresh on 2026-04-25.

Revision ID: 0051
Revises: 0050
Create Date: 2026-04-25
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0051"
down_revision: str | None = "0050"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "sanctions_list_entries",
        "ref_id",
        existing_type=sa.String(length=100),
        type_=sa.String(length=500),
        existing_nullable=False,
    )


def downgrade() -> None:
    # Note: this will fail if any existing ref_id exceeds 100 chars. That's
    # the expected behaviour — you can't downgrade after OpenSanctions data
    # has been ingested without first deleting those rows.
    op.alter_column(
        "sanctions_list_entries",
        "ref_id",
        existing_type=sa.String(length=500),
        type_=sa.String(length=100),
        existing_nullable=False,
    )
