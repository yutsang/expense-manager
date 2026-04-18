"""Bank feed connection API — connect, sync, check status, disconnect."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.api.v1.deps import ActorId, DbSession, TenantId
from app.api.v1.schemas import (
    BankFeedConnectRequest,
    BankFeedStatusResponse,
    BankFeedSyncResponse,
)
from app.services.bank_feeds import (
    BankFeedAlreadyConnectedError,
    BankFeedConnectionNotFoundError,
    create_connection,
    disconnect_feed,
    get_feed_status,
    sync_transactions,
)
from app.services.bank_reconciliation import (
    BankAccountNotFoundError,
    get_bank_account,
)

router = APIRouter(tags=["bank-feeds"])


# ---------------------------------------------------------------------------
# Connect a bank feed
# ---------------------------------------------------------------------------


@router.post(
    "/bank-accounts/{account_id}/connect-feed",
    response_model=BankFeedStatusResponse,
    status_code=status.HTTP_201_CREATED,
)
async def connect_feed(
    account_id: str,
    body: BankFeedConnectRequest,
    db: DbSession,
    tenant_id: TenantId,
    actor_id: ActorId,
):
    """Create a bank feed connection for a bank account."""
    try:
        await get_bank_account(db, tenant_id, account_id)
    except BankAccountNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Bank account not found")

    try:
        conn = await create_connection(
            db,
            tenant_id=tenant_id,
            actor_id=actor_id,
            bank_account_id=account_id,
            provider=body.provider,
            access_token=body.access_token,
            item_id=body.item_id,
            institution_id=body.institution_id,
            institution_name=body.institution_name,
        )
        await db.commit()
        await db.refresh(conn)
        return BankFeedStatusResponse.model_validate(conn)
    except BankFeedAlreadyConnectedError:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="Bank account already has an active feed connection",
        )


# ---------------------------------------------------------------------------
# Feed status
# ---------------------------------------------------------------------------


@router.get(
    "/bank-accounts/{account_id}/feed-status",
    response_model=BankFeedStatusResponse | None,
)
async def feed_status(
    account_id: str,
    db: DbSession,
    tenant_id: TenantId,
):
    """Get the current feed connection status for a bank account."""
    try:
        await get_bank_account(db, tenant_id, account_id)
    except BankAccountNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Bank account not found")

    conn = await get_feed_status(db, tenant_id, account_id)
    if conn is None:
        return None
    return BankFeedStatusResponse.model_validate(conn)


# ---------------------------------------------------------------------------
# Manual sync
# ---------------------------------------------------------------------------


@router.post(
    "/bank-accounts/{account_id}/sync",
    response_model=BankFeedSyncResponse,
)
async def trigger_sync(
    account_id: str,
    db: DbSession,
    tenant_id: TenantId,
    actor_id: ActorId,
):
    """Trigger a manual sync for the bank feed on this account."""
    try:
        await get_bank_account(db, tenant_id, account_id)
    except BankAccountNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Bank account not found")

    conn = await get_feed_status(db, tenant_id, account_id)
    if conn is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail="No active feed connection for this bank account",
        )

    try:
        synced = await sync_transactions(db, tenant_id, conn.id)
        await db.commit()
        await db.refresh(conn)
        return BankFeedSyncResponse(
            connection_id=conn.id,
            status=conn.status,
            transactions_synced=len(synced),
            last_sync_at=conn.last_sync_at,
        )
    except BankFeedConnectionNotFoundError:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail="Feed connection not found",
        )


# ---------------------------------------------------------------------------
# Disconnect
# ---------------------------------------------------------------------------


@router.delete(
    "/bank-accounts/{account_id}/disconnect-feed",
    response_model=BankFeedStatusResponse,
)
async def disconnect(
    account_id: str,
    db: DbSession,
    tenant_id: TenantId,
    actor_id: ActorId,
):
    """Disconnect the bank feed for a bank account."""
    try:
        await get_bank_account(db, tenant_id, account_id)
    except BankAccountNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Bank account not found")

    conn = await get_feed_status(db, tenant_id, account_id)
    if conn is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail="No active feed connection for this bank account",
        )

    try:
        conn = await disconnect_feed(db, tenant_id, conn.id, actor_id=actor_id)
        await db.commit()
        await db.refresh(conn)
        return BankFeedStatusResponse.model_validate(conn)
    except BankFeedConnectionNotFoundError:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail="Feed connection not found",
        )
