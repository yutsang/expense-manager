"""memberships: add invite_token_hash + invite_expires_at

Supports the user-management flow: an owner/admin POSTs an invite, we
generate a one-time token, email the link to the invitee, and they
accept the invite by setting a password. The token is stored as SHA-256
hashes (never plaintext) and expires 7 days after issue.

Revision ID: 0050
Revises: 0049
Create Date: 2026-04-20
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0050"
down_revision: str | None = "0049"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "memberships",
        sa.Column("invite_token_hash", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "memberships",
        sa.Column("invite_expires_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_memberships_invite_token_hash",
        "memberships",
        ["invite_token_hash"],
    )


def downgrade() -> None:
    op.drop_index("ix_memberships_invite_token_hash", table_name="memberships")
    op.drop_column("memberships", "invite_expires_at")
    op.drop_column("memberships", "invite_token_hash")
