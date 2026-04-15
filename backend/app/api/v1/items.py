"""Items and Tax Codes API."""
from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, HTTPException, Query, status

from app.api.v1.deps import ActorId, DbSession, TenantId
from app.api.v1.schemas import (
    ItemCreate,
    ItemListResponse,
    ItemResponse,
    ItemUpdate,
    TaxCodeCreate,
    TaxCodeListResponse,
    TaxCodeResponse,
    TaxCodeUpdate,
)
from app.services.items import (
    ItemCodeConflictError,
    ItemNotFoundError,
    archive_item,
    create_item,
    get_item,
    list_items,
    update_item,
)
from app.services.tax_codes import (
    TaxCodeConflictError,
    TaxCodeNotFoundError,
    create_tax_code,
    get_tax_code,
    list_tax_codes,
    update_tax_code,
)

# ── Items ─────────────────────────────────────────────────────────────────────

router = APIRouter(tags=["items"])
items_router = APIRouter(prefix="/items")
tax_router = APIRouter(prefix="/tax-codes")


@items_router.post("", response_model=ItemResponse, status_code=status.HTTP_201_CREATED)
async def create_item_endpoint(body: ItemCreate, db: DbSession, tenant_id: TenantId, actor_id: ActorId):
    try:
        data = body.model_dump()
        # Convert string prices to Decimal for service layer
        for price_field in ("sales_unit_price", "purchase_unit_price"):
            if data[price_field] is not None:
                data[price_field] = Decimal(data[price_field])
        item = await create_item(db, tenant_id, actor_id, **data)
        await db.commit()
        return item
    except ItemCodeConflictError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc))


@items_router.get("", response_model=ItemListResponse)
async def list_items_endpoint(
    db: DbSession,
    tenant_id: TenantId,
    item_type: str | None = Query(default=None),
    include_archived: bool = Query(default=False),
    limit: int = Query(default=50, le=200),
    cursor: str | None = Query(default=None),
):
    items = await list_items(db, tenant_id, item_type=item_type, include_archived=include_archived, limit=limit + 1, cursor=cursor)
    next_cursor = None
    if len(items) > limit:
        next_cursor = items[limit].id
        items = items[:limit]
    return ItemListResponse(items=items, next_cursor=next_cursor)


@items_router.get("/{item_id}", response_model=ItemResponse)
async def get_item_endpoint(item_id: str, db: DbSession, tenant_id: TenantId):
    try:
        return await get_item(db, tenant_id, item_id)
    except ItemNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Item not found")


@items_router.patch("/{item_id}", response_model=ItemResponse)
async def update_item_endpoint(item_id: str, body: ItemUpdate, db: DbSession, tenant_id: TenantId, actor_id: ActorId):
    try:
        updates = {k: v for k, v in body.model_dump().items() if v is not None}
        for price_field in ("sales_unit_price", "purchase_unit_price"):
            if price_field in updates:
                updates[price_field] = Decimal(updates[price_field])
        item = await update_item(db, tenant_id, item_id, actor_id, updates)
        await db.commit()
        return item
    except ItemNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Item not found")


@items_router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def archive_item_endpoint(item_id: str, db: DbSession, tenant_id: TenantId, actor_id: ActorId):
    try:
        await archive_item(db, tenant_id, item_id, actor_id)
        await db.commit()
    except ItemNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Item not found")


# ── Tax Codes ─────────────────────────────────────────────────────────────────

@tax_router.post("", response_model=TaxCodeResponse, status_code=status.HTTP_201_CREATED)
async def create_tax_code_endpoint(body: TaxCodeCreate, db: DbSession, tenant_id: TenantId, actor_id: ActorId):
    try:
        tc = await create_tax_code(
            db, tenant_id, actor_id,
            code=body.code,
            name=body.name,
            rate=Decimal(body.rate),
            tax_type=body.tax_type,
            country=body.country,
            tax_collected_account_id=body.tax_collected_account_id,
            tax_paid_account_id=body.tax_paid_account_id,
        )
        await db.commit()
        return tc
    except TaxCodeConflictError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc))


@tax_router.get("", response_model=TaxCodeListResponse)
async def list_tax_codes_endpoint(
    db: DbSession,
    tenant_id: TenantId,
    country: str | None = Query(default=None),
    active_only: bool = Query(default=True),
    limit: int = Query(default=100, le=200),
):
    items = await list_tax_codes(db, tenant_id, country=country, active_only=active_only, limit=limit)
    return TaxCodeListResponse(items=items)


@tax_router.get("/{tax_code_id}", response_model=TaxCodeResponse)
async def get_tax_code_endpoint(tax_code_id: str, db: DbSession, tenant_id: TenantId):
    try:
        return await get_tax_code(db, tenant_id, tax_code_id)
    except TaxCodeNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Tax code not found")


@tax_router.patch("/{tax_code_id}", response_model=TaxCodeResponse)
async def update_tax_code_endpoint(tax_code_id: str, body: TaxCodeUpdate, db: DbSession, tenant_id: TenantId, actor_id: ActorId):
    try:
        updates = {k: v for k, v in body.model_dump().items() if v is not None}
        if "rate" in updates:
            updates["rate"] = Decimal(updates["rate"])
        tc = await update_tax_code(db, tenant_id, tax_code_id, actor_id, updates)
        await db.commit()
        return tc
    except TaxCodeNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Tax code not found")


# Combine into one module router
router.include_router(items_router)
router.include_router(tax_router)
