"""payroll: add salary_records table for MPF tracking

Revision ID: 0031
Revises: 0030
Create Date: 2026-04-16
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0031"
down_revision: str | None = "0030"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "salary_records",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column(
            "employee_contact_id",
            sa.UUID(),
            sa.ForeignKey("contacts.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "period_id",
            sa.UUID(),
            sa.ForeignKey("periods.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("gross_salary", sa.Numeric(19, 4), nullable=False),
        sa.Column("employer_mpf", sa.Numeric(19, 4), nullable=False),
        sa.Column("employee_mpf", sa.Numeric(19, 4), nullable=False),
        sa.Column("net_pay", sa.Numeric(19, 4), nullable=False),
        sa.Column("mpf_scheme_name", sa.String(255), nullable=True),
        sa.Column("payment_date", sa.String(10), nullable=True),
        sa.Column(
            "journal_entry_id",
            sa.UUID(),
            sa.ForeignKey("journal_entries.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("gross_salary >= 0", name="ck_salary_records_gross_non_negative"),
        sa.CheckConstraint("employer_mpf >= 0", name="ck_salary_records_employer_mpf_non_negative"),
        sa.CheckConstraint("employee_mpf >= 0", name="ck_salary_records_employee_mpf_non_negative"),
    )
    op.create_index("ix_salary_records_tenant_id", "salary_records", ["tenant_id"])
    op.create_index("ix_salary_records_employee", "salary_records", ["employee_contact_id"])
    op.create_index("ix_salary_records_period", "salary_records", ["period_id"])


def downgrade() -> None:
    op.drop_index("ix_salary_records_period", table_name="salary_records")
    op.drop_index("ix_salary_records_employee", table_name="salary_records")
    op.drop_index("ix_salary_records_tenant_id", table_name="salary_records")
    op.drop_table("salary_records")
