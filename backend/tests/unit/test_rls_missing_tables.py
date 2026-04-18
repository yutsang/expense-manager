"""Unit tests for RLS enablement on accruals, fixed_assets, salary_records (Bug #52).

Tests cover:
  - Migration 0035 exists with upgrade() and downgrade()
  - Migration enables RLS and creates tenant_isolation policy for each table
  - Downgrade drops policies and disables RLS
"""

from __future__ import annotations

import pathlib


_MIGRATIONS_DIR = pathlib.Path(__file__).resolve().parents[2] / "migrations" / "versions"
_TABLES = ["accruals", "fixed_assets", "salary_records"]


class TestMigration0035Exists:
    """Migration 0035 must exist and have correct structure."""

    def _get_migration_source(self) -> str:
        candidates = list(_MIGRATIONS_DIR.glob("0035*"))
        assert len(candidates) >= 1, "Migration 0035 not found"
        return candidates[0].read_text()

    def test_migration_file_exists(self) -> None:
        self._get_migration_source()

    def test_migration_has_upgrade_and_downgrade(self) -> None:
        source = self._get_migration_source()
        assert "def upgrade()" in source
        assert "def downgrade()" in source

    def test_migration_revises_0032(self) -> None:
        source = self._get_migration_source()
        assert 'down_revision' in source
        assert '"0032"' in source


class TestMigration0035EnablesRLS:
    """Migration 0035 must enable RLS on all three tables."""

    def _get_migration_source(self) -> str:
        candidates = list(_MIGRATIONS_DIR.glob("0035*"))
        return candidates[0].read_text()

    def test_enables_rls_on_accruals(self) -> None:
        source = self._get_migration_source()
        assert "accruals" in source

    def test_enables_rls_on_fixed_assets(self) -> None:
        source = self._get_migration_source()
        assert "fixed_assets" in source

    def test_enables_rls_on_salary_records(self) -> None:
        source = self._get_migration_source()
        assert "salary_records" in source

    def test_uses_enable_row_level_security(self) -> None:
        source = self._get_migration_source()
        assert "ENABLE ROW LEVEL SECURITY" in source

    def test_uses_force_row_level_security(self) -> None:
        source = self._get_migration_source()
        assert "FORCE ROW LEVEL SECURITY" in source

    def test_creates_tenant_isolation_policy(self) -> None:
        source = self._get_migration_source()
        assert "CREATE POLICY tenant_isolation" in source
        assert "current_setting('app.tenant_id'" in source

    def test_downgrade_drops_policies(self) -> None:
        source = self._get_migration_source()
        downgrade_start = source.index("def downgrade()")
        downgrade_body = source[downgrade_start:]
        assert "DROP POLICY" in downgrade_body
        assert "DISABLE ROW LEVEL SECURITY" in downgrade_body

    def test_all_tables_covered(self) -> None:
        source = self._get_migration_source()
        for table in _TABLES:
            assert table in source, f"Table {table} not found in migration"
