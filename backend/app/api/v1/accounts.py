"""Accounts API — CRUD and archive."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status

from app.api.v1.deps import ActorId, DbSession, TenantId
from app.api.v1.schemas import (
    AccountCreate,
    AccountListResponse,
    AccountResponse,
    AccountUpdate,
    ProblemDetail,
)
from app.services.accounts import (
    AccountCodeConflictError,
    AccountInUseError,
    AccountNotFoundError,
    archive_account,
    create_account,
    get_account,
    list_accounts,
    update_account,
)

router = APIRouter(prefix="/accounts", tags=["accounts"])


@router.post(
    "",
    response_model=AccountResponse,
    status_code=status.HTTP_201_CREATED,
    responses={409: {"model": ProblemDetail}},
)
async def create_account_endpoint(
    body: AccountCreate,
    db: DbSession,
    tenant_id: TenantId,
    actor_id: ActorId,
) -> AccountResponse:
    try:
        account = await create_account(
            db,
            tenant_id=tenant_id,
            code=body.code,
            name=body.name,
            type=body.type,
            subtype=body.subtype,
            normal_balance=body.normal_balance,
            parent_id=body.parent_id,
            currency=body.currency,
            description=body.description,
            actor_id=actor_id,
        )
        await db.commit()
    except AccountCodeConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except AccountNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return AccountResponse.model_validate(account)


@router.get("", response_model=AccountListResponse)
async def list_accounts_endpoint(
    db: DbSession,
    tenant_id: TenantId,
    include_inactive: bool = Query(default=False),
) -> AccountListResponse:
    accounts = await list_accounts(db, tenant_id=tenant_id, include_inactive=include_inactive)
    return AccountListResponse(
        items=[AccountResponse.model_validate(a) for a in accounts],
        total=len(accounts),
    )


@router.get("/{account_id}", response_model=AccountResponse)
async def get_account_endpoint(
    account_id: str,
    db: DbSession,
    tenant_id: TenantId,
) -> AccountResponse:
    try:
        account = await get_account(db, account_id=account_id, tenant_id=tenant_id)
    except AccountNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return AccountResponse.model_validate(account)


@router.patch("/{account_id}", response_model=AccountResponse)
async def update_account_endpoint(
    account_id: str,
    body: AccountUpdate,
    db: DbSession,
    tenant_id: TenantId,
    actor_id: ActorId,
) -> AccountResponse:
    try:
        account = await update_account(
            db,
            account_id=account_id,
            tenant_id=tenant_id,
            name=body.name,
            description=body.description,
            actor_id=actor_id,
        )
        await db.commit()
    except AccountNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return AccountResponse.model_validate(account)


@router.delete("/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
async def archive_account_endpoint(
    account_id: str,
    db: DbSession,
    tenant_id: TenantId,
    actor_id: ActorId,
) -> None:
    try:
        await archive_account(db, account_id=account_id, tenant_id=tenant_id, actor_id=actor_id)
        await db.commit()
    except AccountNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except AccountInUseError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
