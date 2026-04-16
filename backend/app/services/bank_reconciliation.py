"""Bank reconciliation service — bank accounts, transactions, reconciliations."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.infra.models import BankAccount, BankReconciliation, BankTransaction

log = get_logger(__name__)

_QUANTIZE_4 = Decimal("0.0001")


class BankAccountNotFoundError(ValueError):
    pass


class BankTransactionNotFoundError(ValueError):
    pass


class BankReconciliationNotFoundError(ValueError):
    pass


# ---------------------------------------------------------------------------
# Bank Accounts
# ---------------------------------------------------------------------------


async def list_bank_accounts(
    db: AsyncSession,
    tenant_id: str,
) -> list[BankAccount]:
    q = select(BankAccount).where(BankAccount.tenant_id == tenant_id).order_by(BankAccount.name)
    result = await db.execute(q)
    return list(result.scalars())


async def create_bank_account(
    db: AsyncSession,
    tenant_id: str,
    actor_id: str | None,
    data: dict,
) -> BankAccount:
    account = BankAccount(
        tenant_id=tenant_id,
        name=data["name"],
        bank_name=data.get("bank_name"),
        account_number=data.get("account_number"),
        currency=data.get("currency", "USD"),
        coa_account_id=data.get("coa_account_id"),
        is_active=data.get("is_active", True),
        created_by=actor_id,
        updated_by=actor_id,
    )
    db.add(account)
    await db.flush()
    await db.refresh(account)
    log.info("bank_account.created", tenant_id=tenant_id, bank_account_id=account.id)
    return account


async def get_bank_account(
    db: AsyncSession,
    tenant_id: str,
    account_id: str,
) -> BankAccount:
    account = await db.scalar(
        select(BankAccount).where(
            BankAccount.id == account_id,
            BankAccount.tenant_id == tenant_id,
        )
    )
    if not account:
        raise BankAccountNotFoundError(account_id)
    return account


# ---------------------------------------------------------------------------
# Bank Transactions
# ---------------------------------------------------------------------------


async def list_bank_transactions(
    db: AsyncSession,
    tenant_id: str,
    bank_account_id: str,
    *,
    reconciled: bool | None = None,
) -> list[BankTransaction]:
    q = (
        select(BankTransaction)
        .where(
            BankTransaction.tenant_id == tenant_id,
            BankTransaction.bank_account_id == bank_account_id,
        )
        .order_by(BankTransaction.transaction_date.desc(), BankTransaction.id)
    )
    if reconciled is not None:
        q = q.where(BankTransaction.is_reconciled == reconciled)
    result = await db.execute(q)
    return list(result.scalars())


async def create_bank_transaction(
    db: AsyncSession,
    tenant_id: str,
    actor_id: str | None,
    data: dict,
) -> BankTransaction:
    txn = BankTransaction(
        tenant_id=tenant_id,
        bank_account_id=data["bank_account_id"],
        transaction_date=data["transaction_date"],
        description=data.get("description"),
        reference=data.get("reference"),
        amount=Decimal(str(data["amount"])),
        currency=data["currency"],
        is_reconciled=False,
        created_by=actor_id,
        updated_by=actor_id,
    )
    db.add(txn)
    await db.flush()
    await db.refresh(txn)
    log.info("bank_transaction.created", tenant_id=tenant_id, transaction_id=txn.id)
    return txn


async def _get_transaction(
    db: AsyncSession,
    tenant_id: str,
    transaction_id: str,
) -> BankTransaction:
    txn = await db.scalar(
        select(BankTransaction).where(
            BankTransaction.id == transaction_id,
            BankTransaction.tenant_id == tenant_id,
        )
    )
    if not txn:
        raise BankTransactionNotFoundError(transaction_id)
    return txn


async def match_transaction(
    db: AsyncSession,
    tenant_id: str,
    actor_id: str | None,
    transaction_id: str,
    journal_line_id: str,
) -> BankTransaction:
    """Link a bank transaction to a journal line and mark as reconciled."""
    txn = await _get_transaction(db, tenant_id, transaction_id)
    now = datetime.now(tz=UTC)
    txn.journal_line_id = journal_line_id
    txn.is_reconciled = True
    txn.reconciled_at = now
    txn.updated_by = actor_id
    txn.version += 1
    await db.flush()
    await db.refresh(txn)
    log.info("bank_transaction.matched", tenant_id=tenant_id, transaction_id=transaction_id)
    return txn


async def unmatch_transaction(
    db: AsyncSession,
    tenant_id: str,
    actor_id: str | None,
    transaction_id: str,
) -> BankTransaction:
    """Remove match between a bank transaction and any journal line."""
    txn = await _get_transaction(db, tenant_id, transaction_id)
    txn.journal_line_id = None
    txn.is_reconciled = False
    txn.reconciled_at = None
    txn.updated_by = actor_id
    txn.version += 1
    await db.flush()
    await db.refresh(txn)
    log.info("bank_transaction.unmatched", tenant_id=tenant_id, transaction_id=transaction_id)
    return txn


# ---------------------------------------------------------------------------
# Bank Reconciliations
# ---------------------------------------------------------------------------


async def create_reconciliation(
    db: AsyncSession,
    tenant_id: str,
    actor_id: str | None,
    data: dict,
) -> BankReconciliation:
    statement_balance = Decimal(str(data["statement_closing_balance"]))
    book_balance = Decimal(str(data["book_balance"]))
    difference = (statement_balance - book_balance).quantize(_QUANTIZE_4)

    now = datetime.now(tz=UTC)
    recon = BankReconciliation(
        tenant_id=tenant_id,
        bank_account_id=data["bank_account_id"],
        period_id=data.get("period_id"),
        statement_closing_balance=statement_balance,
        book_balance=book_balance,
        difference=difference,
        status=data.get("status", "in_progress"),
        reconciled_at=now if data.get("status") == "completed" else None,
        reconciled_by=actor_id if data.get("status") == "completed" else None,
        created_by=actor_id,
        updated_by=actor_id,
    )
    db.add(recon)

    # Update the bank account's last reconciled fields if completed
    if data.get("status") == "completed":
        bank_account = await get_bank_account(db, tenant_id, data["bank_account_id"])
        bank_account.last_reconciled_at = now
        bank_account.last_reconciled_balance = statement_balance
        bank_account.updated_by = actor_id
        bank_account.version += 1

    await db.flush()
    await db.refresh(recon)
    log.info("bank_reconciliation.created", tenant_id=tenant_id, reconciliation_id=recon.id)
    return recon


async def list_reconciliations(
    db: AsyncSession,
    tenant_id: str,
    bank_account_id: str,
) -> list[BankReconciliation]:
    q = (
        select(BankReconciliation)
        .where(
            BankReconciliation.tenant_id == tenant_id,
            BankReconciliation.bank_account_id == bank_account_id,
        )
        .order_by(BankReconciliation.created_at.desc())
    )
    result = await db.execute(q)
    return list(result.scalars())
