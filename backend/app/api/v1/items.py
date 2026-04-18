"""Items and Tax Codes API."""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse

from app.api.v1.deps import ActorId, DbSession, TenantId
from app.api.v1.schemas import (
    CsvImportResult,
    ItemCreate,
    ItemListResponse,
    ItemResponse,
    ItemUpdate,
    TaxCodeCreate,
    TaxCodeListResponse,
    TaxCodeResponse,
    TaxCodeUpdate,
)
from app.services.csv_import import generate_template_csv, parse_csv, parse_decimal
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
    TaxCodeInUseError,
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
async def create_item_endpoint(
    body: ItemCreate, db: DbSession, tenant_id: TenantId, actor_id: ActorId
):
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
    items = await list_items(
        db,
        tenant_id,
        item_type=item_type,
        include_archived=include_archived,
        limit=limit + 1,
        cursor=cursor,
    )
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
async def update_item_endpoint(
    item_id: str, body: ItemUpdate, db: DbSession, tenant_id: TenantId, actor_id: ActorId
):
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
async def archive_item_endpoint(
    item_id: str, db: DbSession, tenant_id: TenantId, actor_id: ActorId
) -> None:
    try:
        await archive_item(db, tenant_id, item_id, actor_id)
        await db.commit()
    except ItemNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Item not found")


# ── Items CSV Import / Template ──────────────────────────────────────────────

_ITEM_REQUIRED = ["code", "name"]
_ITEM_OPTIONAL = ["description", "unit_price", "account_code", "tax_code"]
_ITEM_ALL = _ITEM_REQUIRED + _ITEM_OPTIONAL
_ITEM_EXAMPLE = ["ITEM-001", "Widget", "Standard widget", "25.00", "4000", "GST"]


@items_router.get("/csv-template")
async def items_csv_template() -> StreamingResponse:
    """Download a CSV template for item imports."""
    content = generate_template_csv(_ITEM_ALL, _ITEM_EXAMPLE)
    return StreamingResponse(
        iter([content]),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="items-template.csv"'},
    )


@items_router.post("/import", response_model=CsvImportResult, status_code=status.HTTP_201_CREATED)
async def import_items(
    file: UploadFile,
    db: DbSession,
    tenant_id: TenantId,
    actor_id: ActorId,
) -> CsvImportResult:
    """Import items from a CSV file."""
    content = await file.read()
    rows, errors = await parse_csv(content, _ITEM_REQUIRED, _ITEM_OPTIONAL)

    imported = 0
    skipped = 0

    for row_no, row in enumerate(rows, start=2 + len(errors)):
        try:
            price = None
            if row.get("unit_price"):
                price = parse_decimal(row["unit_price"])

            await create_item(
                db,
                tenant_id,
                actor_id,
                code=row["code"],
                name=row["name"],
                item_type="service",
                description=row.get("description") or None,
                sales_unit_price=price,
            )
            imported += 1
        except ItemCodeConflictError:
            skipped += 1
        except Exception as exc:
            errors.append(f"Row {row_no}: {exc}")
            skipped += 1

    if imported > 0:
        await db.commit()

    from app.core.logging import get_logger
    get_logger(__name__).info(
        "items.import.complete",
        tenant_id=tenant_id,
        imported=imported,
        skipped=skipped,
        errors=len(errors),
    )
    return CsvImportResult(imported=imported, skipped=skipped, errors=errors)


# ── Tax Codes ─────────────────────────────────────────────────────────────────


@tax_router.post("", response_model=TaxCodeResponse, status_code=status.HTTP_201_CREATED)
async def create_tax_code_endpoint(
    body: TaxCodeCreate, db: DbSession, tenant_id: TenantId, actor_id: ActorId
):
    try:
        tc = await create_tax_code(
            db,
            tenant_id,
            actor_id,
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
    items = await list_tax_codes(
        db, tenant_id, country=country, active_only=active_only, limit=limit
    )
    return TaxCodeListResponse(items=items)


@tax_router.get("/{tax_code_id}", response_model=TaxCodeResponse)
async def get_tax_code_endpoint(tax_code_id: str, db: DbSession, tenant_id: TenantId):
    try:
        return await get_tax_code(db, tenant_id, tax_code_id)
    except TaxCodeNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Tax code not found")


@tax_router.patch("/{tax_code_id}", response_model=TaxCodeResponse)
async def update_tax_code_endpoint(
    tax_code_id: str, body: TaxCodeUpdate, db: DbSession, tenant_id: TenantId, actor_id: ActorId
):
    try:
        updates = {k: v for k, v in body.model_dump().items() if v is not None}
        if "rate" in updates:
            updates["rate"] = Decimal(updates["rate"])
        tc = await update_tax_code(db, tenant_id, tax_code_id, actor_id, updates)
        await db.commit()
        return tc
    except TaxCodeNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Tax code not found")
    except TaxCodeInUseError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc))


# ── Tax Codes CSV Import / Template ──────────────────────────────────────────

_TAX_REQUIRED = ["code", "name", "rate", "tax_type"]
_TAX_OPTIONAL = ["country"]
_TAX_ALL = _TAX_REQUIRED + _TAX_OPTIONAL
_TAX_EXAMPLE = ["GST", "GST 10%", "0.10", "output", "AU"]


@tax_router.get("/csv-template")
async def tax_csv_template() -> StreamingResponse:
    """Download a CSV template for tax code imports."""
    content = generate_template_csv(_TAX_ALL, _TAX_EXAMPLE)
    return StreamingResponse(
        iter([content]),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="tax-codes-template.csv"'},
    )


@tax_router.post("/import", response_model=CsvImportResult, status_code=status.HTTP_201_CREATED)
async def import_tax_codes(
    file: UploadFile,
    db: DbSession,
    tenant_id: TenantId,
    actor_id: ActorId,
) -> CsvImportResult:
    """Import tax codes from a CSV file."""
    content = await file.read()
    rows, errors = await parse_csv(content, _TAX_REQUIRED, _TAX_OPTIONAL)

    imported = 0
    skipped = 0

    for row_no, row in enumerate(rows, start=2 + len(errors)):
        try:
            tax_type = row["tax_type"].lower()
            if tax_type not in ("output", "input", "exempt", "zero"):
                errors.append(
                    f"Row {row_no}: tax_type must be output/input/exempt/zero, got '{tax_type}'"
                )
                skipped += 1
                continue

            rate = parse_decimal(row["rate"])
            await create_tax_code(
                db,
                tenant_id,
                actor_id,
                code=row["code"],
                name=row["name"],
                rate=rate,
                tax_type=tax_type,
                country=(row.get("country") or "").upper() or "US",
            )
            imported += 1
        except TaxCodeConflictError:
            skipped += 1
        except Exception as exc:
            errors.append(f"Row {row_no}: {exc}")
            skipped += 1

    if imported > 0:
        await db.commit()

    from app.core.logging import get_logger
    get_logger(__name__).info(
        "tax_codes.import.complete",
        tenant_id=tenant_id,
        imported=imported,
        skipped=skipped,
        errors=len(errors),
    )
    return CsvImportResult(imported=imported, skipped=skipped, errors=errors)


# Combine into one module router
router.include_router(items_router)
router.include_router(tax_router)
