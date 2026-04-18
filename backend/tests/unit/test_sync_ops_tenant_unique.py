"""Unit tests for SyncOp per-tenant client_op_id uniqueness (Bug #74).

Tests cover:
  - SyncOp model no longer has global unique=True on client_op_id
  - SyncOp model has UniqueConstraint on (tenant_id, client_op_id)
  - Migration 0038 exists and replaces the constraint correctly
"""

from __future__ import annotations

import pathlib

_MODELS_PATH = pathlib.Path(__file__).resolve().parents[2] / "app" / "infra" / "models.py"
_MIGRATIONS_DIR = pathlib.Path(__file__).resolve().parents[2] / "migrations" / "versions"


class TestSyncOpModelConstraint:
    """SyncOp model must use per-tenant unique constraint."""

    def _get_source(self) -> str:
        return _MODELS_PATH.read_text()

    def _get_sync_op_class(self) -> str:
        source = self._get_source()
        start = source.index("class SyncOp(Base)")
        # Find next class definition
        next_class = source.find("\nclass ", start + 1)
        if next_class == -1:
            next_class = len(source)
        return source[start:next_class]

    def test_no_global_unique_on_client_op_id(self) -> None:
        cls_body = self._get_sync_op_class()
        # Find the client_op_id line
        for line in cls_body.split("\n"):
            if "client_op_id" in line and "mapped_column" in line:
                assert "unique=True" not in line, (
                    "client_op_id should not have unique=True (global scope)"
                )
                break
        else:
            raise AssertionError("client_op_id column not found in SyncOp")

    def test_has_tenant_client_op_unique_constraint(self) -> None:
        cls_body = self._get_sync_op_class()
        assert "uq_sync_ops_tenant_client_op" in cls_body

    def test_constraint_includes_tenant_id(self) -> None:
        cls_body = self._get_sync_op_class()
        # Find the UniqueConstraint with the name
        constraint_start = cls_body.index("uq_sync_ops_tenant_client_op")
        # Go back to find the beginning of the constraint
        constraint_section = cls_body[max(0, constraint_start - 100):constraint_start + 50]
        assert "tenant_id" in constraint_section
        assert "client_op_id" in constraint_section


class TestMigration0038:
    """Migration 0038 must replace global unique with per-tenant unique."""

    def _get_migration_source(self) -> str:
        candidates = list(_MIGRATIONS_DIR.glob("*sync_ops_tenant*"))
        assert len(candidates) >= 1, "Sync ops tenant unique migration not found"
        return candidates[0].read_text()

    def test_migration_exists(self) -> None:
        self._get_migration_source()

    def test_drops_old_constraint(self) -> None:
        source = self._get_migration_source()
        assert "uq_sync_ops_client_op_id" in source
        assert "drop_constraint" in source

    def test_creates_new_tenant_scoped_constraint(self) -> None:
        source = self._get_migration_source()
        assert "uq_sync_ops_tenant_client_op" in source
        assert "create_unique_constraint" in source

    def test_has_downgrade(self) -> None:
        source = self._get_migration_source()
        assert "def downgrade()" in source
        downgrade_start = source.index("def downgrade()")
        downgrade_body = source[downgrade_start:]
        # downgrade should restore original constraint
        assert "uq_sync_ops_client_op_id" in downgrade_body

    def test_migration_has_down_revision(self) -> None:
        source = self._get_migration_source()
        assert "down_revision" in source
