"""Fixed assets API — CRUD + depreciation (Issue #41)."""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.api.v1.deps import ActorId, DbSession, TenantId
from app.services.fixed_assets import create_asset, depreciate_asset, get_asset, list_assets

router = APIRouter(prefix="/assets", tags=["fixed-assets"])


class FixedAssetCreate(BaseModel):
    name: str
    category: str
    acquisition_date: str
    cost: str = Field(..., description="Decimal string, e.g. '12000.0000'")
    residual_value: str = Field(default="0.0000")
    useful_life_months: int
    depreciation_method: str
    asset_account_id: str
    depreciation_account_id: str
    accumulated_depreciation_account_id: str
    description: str | None = None


class FixedAssetResponse(BaseModel):
    id: str
    tenant_id: str
    name: str
    category: str
    acquisition_date: str
    cost: str
    residual_value: str
    useful_life_months: int
    depreciation_method: str
    asset_account_id: str
    depreciation_account_id: str
    accumulated_depreciation_account_id: str
    status: str
    description: str | None = None


class FixedAssetListResponse(BaseModel):
    items: list[FixedAssetResponse]


class DepreciateResponse(BaseModel):
    journal_entry_id: str
    depreciation_amount: str
    description: str


def _to_response(asset: object) -> FixedAssetResponse:
    return FixedAssetResponse(
        id=asset.id,  # type: ignore[union-attr]
        tenant_id=asset.tenant_id,  # type: ignore[union-attr]
        name=asset.name,  # type: ignore[union-attr]
        category=asset.category,  # type: ignore[union-attr]
        acquisition_date=asset.acquisition_date,  # type: ignore[union-attr]
        cost=str(asset.cost),  # type: ignore[union-attr]
        residual_value=str(asset.residual_value),  # type: ignore[union-attr]
        useful_life_months=asset.useful_life_months,  # type: ignore[union-attr]
        depreciation_method=asset.depreciation_method,  # type: ignore[union-attr]
        asset_account_id=asset.asset_account_id,  # type: ignore[union-attr]
        depreciation_account_id=asset.depreciation_account_id,  # type: ignore[union-attr]
        accumulated_depreciation_account_id=asset.accumulated_depreciation_account_id,  # type: ignore[union-attr]
        status=asset.status,  # type: ignore[union-attr]
        description=asset.description,  # type: ignore[union-attr]
    )


@router.post("", response_model=FixedAssetResponse, status_code=status.HTTP_201_CREATED)
async def create_asset_endpoint(
    db: DbSession,
    tenant_id: TenantId,
    actor_id: ActorId,
    body: FixedAssetCreate,
) -> FixedAssetResponse:
    try:
        asset = await create_asset(
            db,
            tenant_id,
            actor_id,
            name=body.name,
            category=body.category,
            acquisition_date=body.acquisition_date,
            cost=Decimal(body.cost),
            residual_value=Decimal(body.residual_value),
            useful_life_months=body.useful_life_months,
            depreciation_method=body.depreciation_method,
            asset_account_id=body.asset_account_id,
            depreciation_account_id=body.depreciation_account_id,
            accumulated_depreciation_account_id=body.accumulated_depreciation_account_id,
            description=body.description,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return _to_response(asset)


@router.get("", response_model=FixedAssetListResponse)
async def list_assets_endpoint(
    db: DbSession,
    tenant_id: TenantId,
    asset_status: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, le=200),
    cursor: str | None = Query(default=None),
) -> FixedAssetListResponse:
    assets = await list_assets(db, tenant_id, status=asset_status, limit=limit, cursor=cursor)
    return FixedAssetListResponse(items=[_to_response(a) for a in assets])


@router.get("/{asset_id}", response_model=FixedAssetResponse)
async def get_asset_endpoint(
    db: DbSession,
    tenant_id: TenantId,
    asset_id: str,
) -> FixedAssetResponse:
    try:
        asset = await get_asset(db, tenant_id, asset_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return _to_response(asset)


@router.post("/{asset_id}/depreciate", response_model=DepreciateResponse)
async def depreciate_asset_endpoint(
    db: DbSession,
    tenant_id: TenantId,
    actor_id: ActorId,
    asset_id: str,
    period_id: str = Query(...),
) -> DepreciateResponse:
    try:
        je = await depreciate_asset(db, tenant_id, actor_id, asset_id=asset_id, period_id=period_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return DepreciateResponse(
        journal_entry_id=je.id,
        depreciation_amount=str(je.total_debit),
        description=je.description,
    )
