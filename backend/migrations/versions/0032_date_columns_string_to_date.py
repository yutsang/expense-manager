"""ledger: change date columns from String(10) to Date type

Revision ID: 0032
Revises: 0031
Create Date: 2026-04-18

Converts Invoice.issue_date, Invoice.due_date, Bill.issue_date,
Bill.due_date, and Payment.payment_date from VARCHAR(10) to DATE.
Existing ISO-8601 date strings (e.g. '2025-01-15') are cast to DATE.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0032"
down_revision: str | None = "0031"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Invoice date columns
    op.alter_column(
        "invoices",
        "issue_date",
        existing_type=sa.String(10),
        type_=sa.Date(),
        postgresql_using="issue_date::date",
        nullable=False,
    )
    op.alter_column(
        "invoices",
        "due_date",
        existing_type=sa.String(10),
        type_=sa.Date(),
        postgresql_using="due_date::date",
        nullable=True,
    )

    # Bill date columns
    op.alter_column(
        "bills",
        "issue_date",
        existing_type=sa.String(10),
        type_=sa.Date(),
        postgresql_using="issue_date::date",
        nullable=False,
    )
    op.alter_column(
        "bills",
        "due_date",
        existing_type=sa.String(10),
        type_=sa.Date(),
        postgresql_using="due_date::date",
        nullable=True,
    )

    # Payment date column
    op.alter_column(
        "payments",
        "payment_date",
        existing_type=sa.String(10),
        type_=sa.Date(),
        postgresql_using="payment_date::date",
        nullable=False,
    )


def downgrade() -> None:
    # Payment date column — revert to String(10)
    op.alter_column(
        "payments",
        "payment_date",
        existing_type=sa.Date(),
        type_=sa.String(10),
        postgresql_using="to_char(payment_date, 'YYYY-MM-DD')",
        nullable=False,
    )

    # Bill date columns — revert to String(10)
    op.alter_column(
        "bills",
        "due_date",
        existing_type=sa.Date(),
        type_=sa.String(10),
        postgresql_using="to_char(due_date, 'YYYY-MM-DD')",
        nullable=True,
    )
    op.alter_column(
        "bills",
        "issue_date",
        existing_type=sa.Date(),
        type_=sa.String(10),
        postgresql_using="to_char(issue_date, 'YYYY-MM-DD')",
        nullable=False,
    )

    # Invoice date columns — revert to String(10)
    op.alter_column(
        "invoices",
        "due_date",
        existing_type=sa.Date(),
        type_=sa.String(10),
        postgresql_using="to_char(due_date, 'YYYY-MM-DD')",
        nullable=True,
    )
    op.alter_column(
        "invoices",
        "issue_date",
        existing_type=sa.Date(),
        type_=sa.String(10),
        postgresql_using="to_char(issue_date, 'YYYY-MM-DD')",
        nullable=False,
    )
