"""Unit tests for bank feed connection lifecycle (Feature #68).

Tests cover:
  - BankFeedConnection model exists with the correct columns
  - BankTransaction model has institution_transaction_id column
  - Migration 0036 exists with upgrade() and downgrade()
  - Service functions are defined (create_connection, sync_transactions, etc.)
  - Service raises BankFeedAlreadyConnectedError on duplicate active connection
  - Service raises BankFeedConnectionNotFoundError when connection is missing
  - disconnect_feed sets status to 'disconnected'
  - sync_transactions returns empty list (placeholder)
  - get_feed_status returns None when no connection exists
  - API router registers expected endpoints
  - Pydantic schemas validate correctly
"""

from __future__ import annotations

import sys
from datetime import UTC
from unittest.mock import AsyncMock, MagicMock

import pytest

_UTC = UTC
_NEEDS_311 = sys.version_info < (3, 11)
_skip_311 = pytest.mark.skipif(_NEEDS_311, reason="datetime.UTC requires Python >=3.11")


# ── Model tests ──────────────────────────────────────────────────────────────


@_skip_311
class TestBankFeedConnectionModel:
    """BankFeedConnection model must exist with the expected columns."""

    def test_model_exists(self) -> None:
        from app.infra.models import BankFeedConnection

        assert BankFeedConnection.__tablename__ == "bank_feed_connections"

    def test_model_has_required_columns(self) -> None:
        from app.infra.models import BankFeedConnection

        table = BankFeedConnection.__table__
        col_names = {c.name for c in table.columns}
        expected = {
            "id",
            "tenant_id",
            "bank_account_id",
            "provider",
            "access_token_encrypted",
            "item_id",
            "institution_id",
            "institution_name",
            "status",
            "last_sync_at",
            "last_sync_cursor",
            "last_error",
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
            "version",
        }
        assert expected.issubset(col_names), f"Missing columns: {expected - col_names}"

    def test_status_check_constraint(self) -> None:
        from app.infra.models import BankFeedConnection

        constraints = [
            c.name
            for c in BankFeedConnection.__table__.constraints
            if hasattr(c, "name") and c.name
        ]
        assert "ck_bank_feed_connections_status" in constraints


@_skip_311
class TestBankTransactionInstitutionId:
    """BankTransaction must have institution_transaction_id column."""

    def test_column_exists(self) -> None:
        from app.infra.models import BankTransaction

        table = BankTransaction.__table__
        col_names = {c.name for c in table.columns}
        assert "institution_transaction_id" in col_names

    def test_column_is_nullable(self) -> None:
        from app.infra.models import BankTransaction

        col = BankTransaction.__table__.columns["institution_transaction_id"]
        assert col.nullable is True


# ── Migration tests ──────────────────────────────────────────────────────────


class TestMigration0036:
    """Migration 0036 must exist and create bank_feed_connections + add column."""

    def _get_migration_source(self) -> str:
        import pathlib

        migrations_dir = pathlib.Path(__file__).resolve().parents[2] / "migrations" / "versions"
        candidates = [f for f in migrations_dir.glob("0036*")]
        assert len(candidates) >= 1, "Migration 0036 not found"
        return candidates[0].read_text()

    def test_migration_file_exists(self) -> None:
        self._get_migration_source()

    def test_migration_has_upgrade_and_downgrade(self) -> None:
        source = self._get_migration_source()
        assert "def upgrade()" in source
        assert "def downgrade()" in source

    def test_migration_creates_bank_feed_connections_table(self) -> None:
        source = self._get_migration_source()
        assert "bank_feed_connections" in source
        assert "create_table" in source

    def test_migration_adds_institution_transaction_id(self) -> None:
        source = self._get_migration_source()
        assert "institution_transaction_id" in source
        assert "bank_transactions" in source

    def test_migration_enables_rls(self) -> None:
        source = self._get_migration_source()
        assert "ENABLE ROW LEVEL SECURITY" in source
        assert "tenant_isolation" in source

    def test_migration_revises_0035(self) -> None:
        source = self._get_migration_source()
        assert '"0035"' in source

    def test_migration_downgrade_drops_table(self) -> None:
        source = self._get_migration_source()
        downgrade_start = source.index("def downgrade()")
        downgrade_body = source[downgrade_start:]
        assert "drop_table" in downgrade_body
        assert "drop_column" in downgrade_body


# ── Service tests ────────────────────────────────────────────────────────────


class TestBankFeedServiceDefinitions:
    """Service module must export expected functions and error classes."""

    def _read_service_source(self) -> str:
        import pathlib

        svc_path = (
            pathlib.Path(__file__).resolve().parents[2] / "app" / "services" / "bank_feeds.py"
        )
        return svc_path.read_text()

    def test_service_file_exists(self) -> None:
        self._read_service_source()

    def test_create_connection_defined(self) -> None:
        source = self._read_service_source()
        assert "async def create_connection" in source

    def test_sync_transactions_defined(self) -> None:
        source = self._read_service_source()
        assert "async def sync_transactions" in source

    def test_get_feed_status_defined(self) -> None:
        source = self._read_service_source()
        assert "async def get_feed_status" in source

    def test_disconnect_feed_defined(self) -> None:
        source = self._read_service_source()
        assert "async def disconnect_feed" in source

    def test_already_connected_error_defined(self) -> None:
        source = self._read_service_source()
        assert "class BankFeedAlreadyConnectedError" in source

    def test_not_found_error_defined(self) -> None:
        source = self._read_service_source()
        assert "class BankFeedConnectionNotFoundError" in source


@_skip_311
class TestCreateConnectionDuplicateCheck:
    """create_connection raises BankFeedAlreadyConnectedError on active duplicate."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        db = AsyncMock()
        db.flush = AsyncMock()
        db.refresh = AsyncMock()
        db.execute = AsyncMock()
        db.scalar = AsyncMock()
        db.add = MagicMock()
        return db

    @pytest.mark.anyio
    async def test_raises_when_active_connection_exists(self, mock_db: AsyncMock) -> None:
        from app.services.bank_feeds import (
            BankFeedAlreadyConnectedError,
            create_connection,
        )

        existing_conn = MagicMock()
        existing_conn.status = "connected"
        mock_db.scalar = AsyncMock(return_value=existing_conn)

        with pytest.raises(BankFeedAlreadyConnectedError):
            await create_connection(
                mock_db,
                tenant_id="t1",
                actor_id="actor-1",
                bank_account_id="ba-1",
                provider="plaid",
                access_token=None,
                item_id=None,
            )

    @pytest.mark.anyio
    async def test_succeeds_when_no_active_connection(self, mock_db: AsyncMock) -> None:
        from app.services.bank_feeds import create_connection

        # First scalar call: no existing connection
        mock_db.scalar = AsyncMock(return_value=None)

        await create_connection(
            mock_db,
            tenant_id="t1",
            actor_id="actor-1",
            bank_account_id="ba-1",
            provider="plaid",
            access_token=None,
            item_id="item-123",
            institution_name="Test Bank",
        )
        mock_db.add.assert_called_once()
        mock_db.flush.assert_awaited_once()


@_skip_311
class TestGetFeedStatusReturnsNone:
    """get_feed_status returns None when no connection exists."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        db = AsyncMock()
        db.scalar = AsyncMock(return_value=None)
        return db

    @pytest.mark.anyio
    async def test_returns_none_when_no_connection(self, mock_db: AsyncMock) -> None:
        from app.services.bank_feeds import get_feed_status

        result = await get_feed_status(mock_db, "t1", "ba-1")
        assert result is None


@_skip_311
class TestDisconnectFeed:
    """disconnect_feed sets status to disconnected."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        db = AsyncMock()
        db.flush = AsyncMock()
        db.refresh = AsyncMock()
        db.scalar = AsyncMock()
        return db

    @pytest.mark.anyio
    async def test_sets_status_to_disconnected(self, mock_db: AsyncMock) -> None:
        from app.services.bank_feeds import disconnect_feed

        conn = MagicMock()
        conn.id = "conn-1"
        conn.tenant_id = "t1"
        conn.status = "connected"
        conn.version = 1
        mock_db.scalar = AsyncMock(return_value=conn)

        result = await disconnect_feed(mock_db, "t1", "conn-1", actor_id="actor-1")
        assert result.status == "disconnected"

    @pytest.mark.anyio
    async def test_raises_not_found_when_missing(self, mock_db: AsyncMock) -> None:
        from app.services.bank_feeds import (
            BankFeedConnectionNotFoundError,
            disconnect_feed,
        )

        mock_db.scalar = AsyncMock(return_value=None)

        with pytest.raises(BankFeedConnectionNotFoundError):
            await disconnect_feed(mock_db, "t1", "nonexistent")


@_skip_311
class TestSyncTransactions:
    """sync_transactions placeholder returns empty list and updates last_sync_at."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        db = AsyncMock()
        db.flush = AsyncMock()
        db.refresh = AsyncMock()
        db.scalar = AsyncMock()
        return db

    @pytest.mark.anyio
    async def test_returns_empty_list(self, mock_db: AsyncMock) -> None:
        from app.services.bank_feeds import sync_transactions

        conn = MagicMock()
        conn.id = "conn-1"
        conn.tenant_id = "t1"
        conn.status = "connected"
        conn.version = 1
        conn.last_sync_at = None
        mock_db.scalar = AsyncMock(return_value=conn)

        result = await sync_transactions(mock_db, "t1", "conn-1")
        assert result == []

    @pytest.mark.anyio
    async def test_updates_last_sync_at(self, mock_db: AsyncMock) -> None:
        from app.services.bank_feeds import sync_transactions

        conn = MagicMock()
        conn.id = "conn-1"
        conn.tenant_id = "t1"
        conn.status = "connected"
        conn.version = 1
        conn.last_sync_at = None
        mock_db.scalar = AsyncMock(return_value=conn)

        await sync_transactions(mock_db, "t1", "conn-1")
        assert conn.last_sync_at is not None

    @pytest.mark.anyio
    async def test_raises_not_found_when_missing(self, mock_db: AsyncMock) -> None:
        from app.services.bank_feeds import (
            BankFeedConnectionNotFoundError,
            sync_transactions,
        )

        mock_db.scalar = AsyncMock(return_value=None)

        with pytest.raises(BankFeedConnectionNotFoundError):
            await sync_transactions(mock_db, "t1", "nonexistent")


# ── API router tests ─────────────────────────────────────────────────────────


class TestBankFeedsApiRouter:
    """API router must register expected endpoints."""

    def _read_api_source(self) -> str:
        import pathlib

        api_path = (
            pathlib.Path(__file__).resolve().parents[2] / "app" / "api" / "v1" / "bank_feeds.py"
        )
        return api_path.read_text()

    def test_connect_feed_endpoint(self) -> None:
        source = self._read_api_source()
        assert "connect-feed" in source
        assert "async def connect_feed" in source

    def test_feed_status_endpoint(self) -> None:
        source = self._read_api_source()
        assert "feed-status" in source
        assert "async def feed_status" in source

    def test_sync_endpoint(self) -> None:
        source = self._read_api_source()
        assert "/sync" in source
        assert "async def trigger_sync" in source

    def test_disconnect_endpoint(self) -> None:
        source = self._read_api_source()
        assert "disconnect-feed" in source
        assert "async def disconnect" in source

    def test_handles_already_connected_409(self) -> None:
        source = self._read_api_source()
        assert "BankFeedAlreadyConnectedError" in source
        assert "409" in source or "HTTP_409_CONFLICT" in source

    def test_handles_account_not_found_404(self) -> None:
        source = self._read_api_source()
        assert "BankAccountNotFoundError" in source
        assert "404" in source or "HTTP_404_NOT_FOUND" in source


# ── Router registration test ─────────────────────────────────────────────────


class TestBankFeedsRouterRegistered:
    """bank_feeds router must be included in main.py."""

    def _read_main_source(self) -> str:
        import pathlib

        main_path = pathlib.Path(__file__).resolve().parents[2] / "app" / "main.py"
        return main_path.read_text()

    def test_import_exists(self) -> None:
        source = self._read_main_source()
        assert "bank_feeds" in source

    def test_router_registered(self) -> None:
        source = self._read_main_source()
        assert "bank_feeds.router" in source


# ── Schema tests ─────────────────────────────────────────────────────────────


class TestBankFeedSchemas:
    """Pydantic schemas for bank feeds must validate correctly."""

    def test_connect_request_defaults(self) -> None:
        from app.api.v1.schemas import BankFeedConnectRequest

        req = BankFeedConnectRequest()
        assert req.provider == "plaid"
        assert req.access_token is None
        assert req.item_id is None

    def test_connect_request_custom(self) -> None:
        from app.api.v1.schemas import BankFeedConnectRequest

        req = BankFeedConnectRequest(
            provider="plaid",
            access_token="tok_123",
            item_id="item_abc",
            institution_id="ins_1",
            institution_name="Chase",
        )
        assert req.provider == "plaid"
        assert req.access_token == "tok_123"
        assert req.institution_name == "Chase"

    def test_status_response_from_attributes(self) -> None:
        from app.api.v1.schemas import BankFeedStatusResponse

        assert BankFeedStatusResponse.model_config.get("from_attributes") is True

    def test_sync_response_fields(self) -> None:
        from app.api.v1.schemas import BankFeedSyncResponse

        resp = BankFeedSyncResponse(
            connection_id="c-1",
            status="connected",
            transactions_synced=0,
            last_sync_at=None,
        )
        assert resp.transactions_synced == 0
        assert resp.status == "connected"
