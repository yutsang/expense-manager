"""Bank feed connection service — manage connections to bank feed providers (e.g. Plaid)."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.infra.models import BankFeedConnection

log = get_logger(__name__)


class BankFeedConnectionNotFoundError(ValueError):
    pass


class BankFeedAlreadyConnectedError(ValueError):
    """Raised when a bank account already has an active feed connection."""

    pass


# ---------------------------------------------------------------------------
# Create connection
# ---------------------------------------------------------------------------


async def create_connection(
    db: AsyncSession,
    tenant_id: str,
    actor_id: str | None,
    bank_account_id: str,
    provider: str,
    access_token: str | None,
    item_id: str | None,
    institution_id: str | None = None,
    institution_name: str | None = None,
) -> BankFeedConnection:
    """Create a new bank feed connection for a bank account.

    Raises BankFeedAlreadyConnectedError if an active connection already exists.
    """
    # Check for existing active connection on this bank account
    existing = await db.scalar(
        select(BankFeedConnection).where(
            BankFeedConnection.tenant_id == tenant_id,
            BankFeedConnection.bank_account_id == bank_account_id,
            BankFeedConnection.status.in_(["connected", "error", "expired"]),
        )
    )
    if existing:
        raise BankFeedAlreadyConnectedError(
            f"Bank account {bank_account_id} already has an active feed connection"
        )

    conn = BankFeedConnection(
        tenant_id=tenant_id,
        bank_account_id=bank_account_id,
        provider=provider,
        access_token_encrypted=access_token,
        item_id=item_id,
        institution_id=institution_id,
        institution_name=institution_name,
        status="connected",
        created_by=actor_id,
        updated_by=actor_id,
    )
    db.add(conn)
    await db.flush()
    await db.refresh(conn)
    log.info(
        "bank_feed.connected",
        tenant_id=tenant_id,
        bank_account_id=bank_account_id,
        provider=provider,
    )
    return conn


# ---------------------------------------------------------------------------
# Sync transactions (placeholder)
# ---------------------------------------------------------------------------


async def sync_transactions(
    db: AsyncSession,
    tenant_id: str,
    connection_id: str,
) -> list[dict]:
    """Sync transactions from the bank feed provider.

    This is a placeholder that would call the Plaid Transactions API
    (or another provider). For now, it updates last_sync_at and returns
    an empty list.
    """
    conn = await _get_connection(db, tenant_id, connection_id)

    now = datetime.now(tz=UTC)
    conn.last_sync_at = now
    conn.updated_at = now
    conn.version += 1

    await db.flush()
    await db.refresh(conn)

    log.info(
        "bank_feed.synced",
        tenant_id=tenant_id,
        connection_id=connection_id,
        transactions_count=0,
    )
    return []


# ---------------------------------------------------------------------------
# Feed status
# ---------------------------------------------------------------------------


async def get_feed_status(
    db: AsyncSession,
    tenant_id: str,
    bank_account_id: str,
) -> BankFeedConnection | None:
    """Return the active feed connection for a bank account, or None if none exists."""
    conn = await db.scalar(
        select(BankFeedConnection).where(
            BankFeedConnection.tenant_id == tenant_id,
            BankFeedConnection.bank_account_id == bank_account_id,
            BankFeedConnection.status != "disconnected",
        )
    )
    return conn


# ---------------------------------------------------------------------------
# Disconnect
# ---------------------------------------------------------------------------


async def disconnect_feed(
    db: AsyncSession,
    tenant_id: str,
    connection_id: str,
    actor_id: str | None = None,
) -> BankFeedConnection:
    """Mark a bank feed connection as disconnected."""
    conn = await _get_connection(db, tenant_id, connection_id)

    now = datetime.now(tz=UTC)
    conn.status = "disconnected"
    conn.updated_at = now
    conn.updated_by = actor_id
    conn.version += 1

    await db.flush()
    await db.refresh(conn)

    log.info(
        "bank_feed.disconnected",
        tenant_id=tenant_id,
        connection_id=connection_id,
    )
    return conn


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _get_connection(
    db: AsyncSession,
    tenant_id: str,
    connection_id: str,
) -> BankFeedConnection:
    conn = await db.scalar(
        select(BankFeedConnection).where(
            BankFeedConnection.id == connection_id,
            BankFeedConnection.tenant_id == tenant_id,
        )
    )
    if not conn:
        raise BankFeedConnectionNotFoundError(connection_id)
    return conn
