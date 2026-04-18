"""projects: add projects, time_entries, billing_rates tables

Revision ID: 0044
Revises: 0043
Create Date: 2026-04-18
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0046"
down_revision: str | None = "0045"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── Projects ─────────────────────────────────────────────────────────
    op.create_table(
        "projects",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "tenant_id",
            sa.UUID(),
            sa.ForeignKey("tenants.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "contact_id",
            sa.UUID(),
            sa.ForeignKey("contacts.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("code", sa.String(50), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("budget_hours", sa.Numeric(10, 2), nullable=True),
        sa.Column("budget_amount", sa.Numeric(19, 4), nullable=True),
        sa.Column("currency", sa.String(3), nullable=False, server_default="USD"),
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
        sa.UniqueConstraint("tenant_id", "code", name="uq_projects_tenant_code"),
        sa.CheckConstraint(
            "status IN ('active','completed','archived')",
            name="ck_projects_status",
        ),
    )
    op.create_index("ix_projects_tenant_id", "projects", ["tenant_id"])
    op.create_index("ix_projects_contact_id", "projects", ["contact_id"])

    # ── Time Entries ─────────────────────────────────────────────────────
    op.create_table(
        "time_entries",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "tenant_id",
            sa.UUID(),
            sa.ForeignKey("tenants.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "project_id",
            sa.UUID(),
            sa.ForeignKey("projects.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("entry_date", sa.Date(), nullable=False),
        sa.Column("hours", sa.Numeric(6, 2), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_billable", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "approval_status",
            sa.String(20),
            nullable=False,
            server_default="pending",
        ),
        sa.Column(
            "billed_invoice_id",
            sa.UUID(),
            sa.ForeignKey("invoices.id", ondelete="SET NULL"),
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
        sa.CheckConstraint(
            "approval_status IN ('pending','approved','rejected')",
            name="ck_time_entries_approval_status",
        ),
        sa.CheckConstraint("hours > 0", name="ck_time_entries_hours_positive"),
    )
    op.create_index("ix_time_entries_tenant_id", "time_entries", ["tenant_id"])
    op.create_index("ix_time_entries_project_id", "time_entries", ["project_id"])
    op.create_index("ix_time_entries_user_id", "time_entries", ["user_id"])
    op.create_index(
        "ix_time_entries_billed_invoice_id", "time_entries", ["billed_invoice_id"]
    )

    # ── Billing Rates ────────────────────────────────────────────────────
    op.create_table(
        "billing_rates",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "tenant_id",
            sa.UUID(),
            sa.ForeignKey("tenants.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "project_id",
            sa.UUID(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("user_id", sa.UUID(), nullable=True),
        sa.Column("role", sa.String(50), nullable=True),
        sa.Column("rate", sa.Numeric(19, 4), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="USD"),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date(), nullable=True),
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
        sa.CheckConstraint("rate >= 0", name="ck_billing_rates_rate_non_negative"),
    )
    op.create_index("ix_billing_rates_tenant_id", "billing_rates", ["tenant_id"])
    op.create_index("ix_billing_rates_project_id", "billing_rates", ["project_id"])
    op.create_index("ix_billing_rates_user_id", "billing_rates", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_billing_rates_user_id", table_name="billing_rates")
    op.drop_index("ix_billing_rates_project_id", table_name="billing_rates")
    op.drop_index("ix_billing_rates_tenant_id", table_name="billing_rates")
    op.drop_table("billing_rates")

    op.drop_index("ix_time_entries_billed_invoice_id", table_name="time_entries")
    op.drop_index("ix_time_entries_user_id", table_name="time_entries")
    op.drop_index("ix_time_entries_project_id", table_name="time_entries")
    op.drop_index("ix_time_entries_tenant_id", table_name="time_entries")
    op.drop_table("time_entries")

    op.drop_index("ix_projects_contact_id", table_name="projects")
    op.drop_index("ix_projects_tenant_id", table_name="projects")
    op.drop_table("projects")
