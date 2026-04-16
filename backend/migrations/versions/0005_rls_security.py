"""rls_security: add RLS policies to Phase 2 tables + approval index

Revision ID: 0005
Revises: 0004
Create Date: 2026-04-15
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = [
    "contacts",
    "items",
    "tax_codes",
    "invoices",
    "invoice_lines",
    "bills",
    "bill_lines",
    "payments",
    "payment_allocations",
]


def upgrade() -> None:
    for table in _TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(f"""
            CREATE POLICY tenant_isolation ON {table}
            USING (tenant_id = current_setting('app.tenant_id', true)::uuid)
        """)

    # Partial index for approval queue queries
    op.execute(
        "CREATE INDEX ix_bills_awaiting ON bills (tenant_id) WHERE status = 'awaiting_approval'"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_bills_awaiting")

    for table in reversed(_TABLES):
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
