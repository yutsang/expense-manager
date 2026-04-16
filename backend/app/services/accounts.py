"""Account service — CRUD, archive, tree validation."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.emitter import emit
from app.core.logging import get_logger
from app.infra.models import Account, JournalLine

log = get_logger(__name__)


class AccountNotFoundError(ValueError):
    pass


class AccountCodeConflictError(ValueError):
    pass


class AccountCycleError(ValueError):
    pass


class AccountInUseError(ValueError):
    pass


async def create_account(
    db: AsyncSession,
    *,
    tenant_id: str,
    code: str,
    name: str,
    type: str,
    subtype: str,
    normal_balance: str,
    parent_id: str | None = None,
    is_system: bool = False,
    currency: str | None = None,
    description: str | None = None,
    actor_id: str | None = None,
) -> Account:
    # Check code uniqueness
    existing = await db.execute(
        select(Account).where(Account.tenant_id == tenant_id, Account.code == code)
    )
    if existing.scalar_one_or_none():
        raise AccountCodeConflictError(f"Account code '{code}' already exists in this tenant")

    # Validate parent exists in this tenant
    if parent_id:
        parent = await db.execute(
            select(Account).where(Account.id == parent_id, Account.tenant_id == tenant_id)
        )
        if not parent.scalar_one_or_none():
            raise AccountNotFoundError(f"Parent account {parent_id} not found")

    account = Account(
        id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        code=code,
        name=name,
        type=type,
        subtype=subtype,
        normal_balance=normal_balance,
        parent_id=parent_id,
        is_system=is_system,
        currency=currency,
        description=description,
        created_at=datetime.now(tz=UTC),
        updated_at=datetime.now(tz=UTC),
        created_by=actor_id,
        updated_by=actor_id,
    )
    db.add(account)
    await db.flush()

    await emit(
        db,
        action="account.create",
        entity_type="account",
        entity_id=account.id,
        actor_type="user" if actor_id else "system",
        actor_id=actor_id,
        tenant_id=tenant_id,
        after={"code": code, "name": name, "type": type},
    )
    log.info("account_created", code=code, tenant_id=tenant_id)
    return account


async def get_account(db: AsyncSession, *, account_id: str, tenant_id: str) -> Account:
    result = await db.execute(
        select(Account).where(Account.id == account_id, Account.tenant_id == tenant_id)
    )
    account = result.scalar_one_or_none()
    if not account:
        raise AccountNotFoundError(f"Account {account_id} not found")
    return account


async def list_accounts(
    db: AsyncSession, *, tenant_id: str, include_inactive: bool = False
) -> list[Account]:
    q = select(Account).where(Account.tenant_id == tenant_id)
    if not include_inactive:
        q = q.where(Account.is_active.is_(True))
    q = q.order_by(Account.code)
    result = await db.execute(q)
    return list(result.scalars().all())


async def update_account(
    db: AsyncSession,
    *,
    account_id: str,
    tenant_id: str,
    name: str | None = None,
    description: str | None = None,
    actor_id: str | None = None,
) -> Account:
    account = await get_account(db, account_id=account_id, tenant_id=tenant_id)
    if account.is_system:
        raise ValueError("System accounts cannot be edited")

    before = {"name": account.name, "description": account.description}
    if name is not None:
        account.name = name
    if description is not None:
        account.description = description
    account.updated_at = datetime.now(tz=UTC)
    account.updated_by = actor_id
    account.version += 1
    await db.flush()

    await emit(
        db,
        action="account.update",
        entity_type="account",
        entity_id=account_id,
        actor_type="user" if actor_id else "system",
        actor_id=actor_id,
        tenant_id=tenant_id,
        before=before,
        after={"name": account.name, "description": account.description},
    )
    return account


async def archive_account(
    db: AsyncSession, *, account_id: str, tenant_id: str, actor_id: str | None = None
) -> Account:
    account = await get_account(db, account_id=account_id, tenant_id=tenant_id)
    if account.is_system:
        raise ValueError("System accounts cannot be archived")

    # Check if account has any posted journal lines
    result = await db.execute(
        select(JournalLine).where(JournalLine.account_id == account_id).limit(1)
    )
    if result.scalar_one_or_none():
        raise AccountInUseError(
            f"Account {account.code} has journal lines — deactivate, don't delete"
        )

    account.is_active = False
    account.updated_at = datetime.now(tz=UTC)
    account.updated_by = actor_id
    account.version += 1
    await db.flush()

    await emit(
        db,
        action="account.archive",
        entity_type="account",
        entity_id=account_id,
        actor_type="user" if actor_id else "system",
        actor_id=actor_id,
        tenant_id=tenant_id,
        before={"is_active": True},
        after={"is_active": False},
    )
    return account


async def seed_coa_from_template(
    db: AsyncSession, *, tenant_id: str, country: str
) -> list[Account]:
    """Provision the Chart of Accounts from the country template. Idempotent."""
    from app.infra.templates import get_coa_template

    template = get_coa_template(country)
    # Build code→id map for parent resolution
    code_to_id: dict[str, str] = {}
    created: list[Account] = []

    # First pass: create all accounts without parents
    for entry in template:
        if "parent_code" not in entry:
            acct = await create_account(
                db,
                tenant_id=tenant_id,
                code=entry["code"],
                name=entry["name"],
                type=entry["type"],
                subtype=entry.get("subtype", "other"),
                normal_balance=entry["normal_balance"],
                is_system=entry.get("is_system", False),
                currency=entry.get("currency"),
                description=entry.get("description"),
            )
            code_to_id[entry["code"]] = acct.id
            created.append(acct)

    # Second pass: accounts with parents
    for entry in template:
        if "parent_code" in entry:
            parent_id = code_to_id.get(entry["parent_code"])
            acct = await create_account(
                db,
                tenant_id=tenant_id,
                code=entry["code"],
                name=entry["name"],
                type=entry["type"],
                subtype=entry.get("subtype", "other"),
                normal_balance=entry["normal_balance"],
                parent_id=parent_id,
                is_system=entry.get("is_system", False),
                currency=entry.get("currency"),
                description=entry.get("description"),
            )
            code_to_id[entry["code"]] = acct.id
            created.append(acct)

    log.info("coa_seeded", tenant_id=tenant_id, country=country, count=len(created))
    return created
