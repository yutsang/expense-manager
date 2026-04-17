"""Bank accounts, transactions, and reconciliation API."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, UploadFile, status

from app.api.v1.deps import ActorId, DbSession, TenantId
from app.api.v1.schemas import (
    BankAccountCreate,
    BankAccountResponse,
    BankImportResult,
    BankReconciliationCreate,
    BankReconciliationResponse,
    BankTransactionCreate,
    BankTransactionResponse,
    MatchTransactionRequest,
)
from app.services.bank_import import import_csv
from app.services.bank_reconciliation import (
    BankAccountNotFoundError,
    BankTransactionNotFoundError,
    DuplicateReconciliationError,
    create_bank_account,
    create_bank_transaction,
    create_reconciliation,
    get_bank_account,
    list_bank_accounts,
    list_bank_transactions,
    list_reconciliations,
    match_transaction,
    unmatch_transaction,
)

router = APIRouter(tags=["bank-reconciliation"])


# ---------------------------------------------------------------------------
# Bank Accounts
# ---------------------------------------------------------------------------


@router.get("/bank-accounts", response_model=list[BankAccountResponse])
async def list_accounts(db: DbSession, tenant_id: TenantId):
    accounts = await list_bank_accounts(db, tenant_id)
    return [BankAccountResponse.model_validate(a) for a in accounts]


@router.post(
    "/bank-accounts", response_model=BankAccountResponse, status_code=status.HTTP_201_CREATED
)
async def create_account(
    body: BankAccountCreate, db: DbSession, tenant_id: TenantId, actor_id: ActorId
):
    account = await create_bank_account(db, tenant_id, actor_id, body.model_dump())
    await db.commit()
    await db.refresh(account)
    return BankAccountResponse.model_validate(account)


@router.get("/bank-accounts/{account_id}", response_model=BankAccountResponse)
async def get_account(account_id: str, db: DbSession, tenant_id: TenantId):
    try:
        account = await get_bank_account(db, tenant_id, account_id)
        return BankAccountResponse.model_validate(account)
    except BankAccountNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Bank account not found")


# ---------------------------------------------------------------------------
# Bank Transactions
# ---------------------------------------------------------------------------


@router.get(
    "/bank-accounts/{account_id}/transactions", response_model=list[BankTransactionResponse]
)
async def list_transactions(
    account_id: str,
    db: DbSession,
    tenant_id: TenantId,
    reconciled: bool | None = Query(default=None),
):
    try:
        await get_bank_account(db, tenant_id, account_id)
    except BankAccountNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Bank account not found")
    txns = await list_bank_transactions(db, tenant_id, account_id, reconciled=reconciled)
    return [BankTransactionResponse.model_validate(t) for t in txns]


@router.post(
    "/bank-accounts/{account_id}/transactions",
    response_model=BankTransactionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_transaction(
    account_id: str,
    body: BankTransactionCreate,
    db: DbSession,
    tenant_id: TenantId,
    actor_id: ActorId,
):
    try:
        await get_bank_account(db, tenant_id, account_id)
    except BankAccountNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Bank account not found")
    data = body.model_dump()
    data["bank_account_id"] = account_id
    txn = await create_bank_transaction(db, tenant_id, actor_id, data)
    await db.commit()
    await db.refresh(txn)
    return BankTransactionResponse.model_validate(txn)


@router.post("/bank-transactions/{transaction_id}/match", response_model=BankTransactionResponse)
async def match(
    transaction_id: str,
    body: MatchTransactionRequest,
    db: DbSession,
    tenant_id: TenantId,
    actor_id: ActorId,
):
    try:
        txn = await match_transaction(db, tenant_id, actor_id, transaction_id, body.journal_line_id)
        await db.commit()
        await db.refresh(txn)
        return BankTransactionResponse.model_validate(txn)
    except BankTransactionNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Bank transaction not found")
    except DuplicateReconciliationError:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="Journal line is already reconciled with another bank transaction",
        )


@router.delete("/bank-transactions/{transaction_id}/match", response_model=BankTransactionResponse)
async def unmatch(
    transaction_id: str,
    db: DbSession,
    tenant_id: TenantId,
    actor_id: ActorId,
):
    try:
        txn = await unmatch_transaction(db, tenant_id, actor_id, transaction_id)
        await db.commit()
        await db.refresh(txn)
        return BankTransactionResponse.model_validate(txn)
    except BankTransactionNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Bank transaction not found")


# ---------------------------------------------------------------------------
# Bank Statement CSV Import
# ---------------------------------------------------------------------------


@router.post(
    "/bank-accounts/{account_id}/import",
    response_model=BankImportResult,
    status_code=status.HTTP_201_CREATED,
)
async def import_bank_statement(
    account_id: str,
    file: UploadFile,
    db: DbSession,
    tenant_id: TenantId,
    actor_id: ActorId,
    currency: str = Query(default="USD"),
) -> BankImportResult:
    """Upload a bank statement CSV and import transactions."""
    try:
        await get_bank_account(db, tenant_id, account_id)
    except BankAccountNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Bank account not found")

    content = await file.read()
    result = await import_csv(
        db,
        tenant_id=tenant_id,
        actor_id=actor_id,
        bank_account_id=account_id,
        csv_bytes=content,
        currency=currency,
    )
    await db.commit()
    return BankImportResult(**result)


# ---------------------------------------------------------------------------
# Bank Reconciliations
# ---------------------------------------------------------------------------


@router.get(
    "/bank-accounts/{account_id}/reconciliations",
    response_model=list[BankReconciliationResponse],
)
async def list_recons(account_id: str, db: DbSession, tenant_id: TenantId):
    try:
        await get_bank_account(db, tenant_id, account_id)
    except BankAccountNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Bank account not found")
    recons = await list_reconciliations(db, tenant_id, account_id)
    return [BankReconciliationResponse.model_validate(r) for r in recons]


@router.post(
    "/bank-accounts/{account_id}/reconciliations",
    response_model=BankReconciliationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_recon(
    account_id: str,
    body: BankReconciliationCreate,
    db: DbSession,
    tenant_id: TenantId,
    actor_id: ActorId,
):
    try:
        await get_bank_account(db, tenant_id, account_id)
    except BankAccountNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Bank account not found")
    data = body.model_dump()
    data["bank_account_id"] = account_id
    recon = await create_reconciliation(db, tenant_id, actor_id, data)
    await db.commit()
    await db.refresh(recon)
    return BankReconciliationResponse.model_validate(recon)
