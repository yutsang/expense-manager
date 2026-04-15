"""Item (product/service) CRUD service."""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.infra.models import Item

log = get_logger(__name__)


class ItemNotFoundError(ValueError):
    pass


class ItemCodeConflictError(ValueError):
    pass


async def create_item(
    db: AsyncSession,
    tenant_id: str,
    actor_id: str | None,
    *,
    code: str,
    name: str,
    item_type: str,
    description: str | None = None,
    unit_of_measure: str | None = None,
    sales_unit_price: Decimal | None = None,
    purchase_unit_price: Decimal | None = None,
    currency: str = "USD",
    sales_account_id: str | None = None,
    cogs_account_id: str | None = None,
    purchase_account_id: str | None = None,
    is_tracked: bool = False,
) -> Item:
    exists = await db.scalar(
        select(Item.id).where(
            Item.tenant_id == tenant_id,
            Item.code == code,
            Item.is_archived.is_(False),
        )
    )
    if exists:
        raise ItemCodeConflictError(f"Item code '{code}' already in use")

    item = Item(
        tenant_id=tenant_id,
        code=code,
        name=name,
        item_type=item_type,
        description=description,
        unit_of_measure=unit_of_measure,
        sales_unit_price=sales_unit_price,
        purchase_unit_price=purchase_unit_price,
        currency=currency,
        sales_account_id=sales_account_id,
        cogs_account_id=cogs_account_id,
        purchase_account_id=purchase_account_id,
        is_tracked=is_tracked,
        created_by=actor_id,
        updated_by=actor_id,
    )
    db.add(item)
    await db.flush()
    await db.refresh(item)
    log.info("item.created", tenant_id=tenant_id, item_id=item.id)
    return item


async def list_items(
    db: AsyncSession,
    tenant_id: str,
    *,
    item_type: str | None = None,
    include_archived: bool = False,
    limit: int = 50,
    cursor: str | None = None,
) -> list[Item]:
    q = select(Item).where(Item.tenant_id == tenant_id)
    if item_type:
        q = q.where(Item.item_type == item_type)
    if not include_archived:
        q = q.where(Item.is_archived.is_(False))
    if cursor:
        q = q.where(Item.id > cursor)
    q = q.order_by(Item.code, Item.id).limit(limit)
    result = await db.execute(q)
    return list(result.scalars())


async def get_item(db: AsyncSession, tenant_id: str, item_id: str) -> Item:
    item = await db.scalar(
        select(Item).where(Item.id == item_id, Item.tenant_id == tenant_id)
    )
    if not item:
        raise ItemNotFoundError(item_id)
    return item


async def update_item(
    db: AsyncSession, tenant_id: str, item_id: str, actor_id: str | None, updates: dict
) -> Item:
    item = await get_item(db, tenant_id, item_id)
    allowed = {
        "name", "description", "unit_of_measure", "sales_unit_price",
        "purchase_unit_price", "currency", "sales_account_id", "cogs_account_id",
        "purchase_account_id", "is_tracked",
    }
    for key, val in updates.items():
        if key in allowed:
            setattr(item, key, val)
    item.updated_by = actor_id
    item.version += 1
    await db.flush()
    await db.refresh(item)
    return item


async def archive_item(
    db: AsyncSession, tenant_id: str, item_id: str, actor_id: str | None
) -> Item:
    item = await get_item(db, tenant_id, item_id)
    item.is_archived = True
    item.updated_by = actor_id
    item.version += 1
    await db.flush()
    return item
