"""FX Rates API — upsert, list, lookup, and timestamped rate resolution."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from app.api.v1.deps import DbSession, TenantId
from app.api.v1.schemas import FxRateResponse, FxRateUpsert
from app.infra.models import FxRate
from app.services.fx import (
    FxRateNotFoundError,
    FxRateSanityError,
    get_rate,
    get_rate_at,
    upsert_rate,
)

router = APIRouter(prefix="/fx", tags=["fx"])


@router.get("/rates", response_model=list[FxRateResponse], status_code=status.HTTP_200_OK)
async def list_fx_rates(
    db: DbSession,
    tenant_id: TenantId,
    limit: int = Query(default=200, ge=1, le=500),
) -> list[FxRate]:
    result = await db.execute(
        select(FxRate)
        .order_by(FxRate.from_currency, FxRate.to_currency, FxRate.rate_date.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


@router.put("/rates", response_model=FxRateResponse, status_code=status.HTTP_200_OK)
async def upsert_fx_rate(
    body: FxRateUpsert,
    db: DbSession,
    tenant_id: TenantId,
) -> FxRateResponse:
    try:
        rate = await upsert_rate(
            db,
            from_currency=body.from_currency,
            to_currency=body.to_currency,
            rate_date=body.rate_date,
            rate=Decimal(body.rate),
            source=body.source,
            force=body.force,
        )
    except FxRateSanityError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    await db.commit()
    return FxRateResponse.model_validate(rate)


@router.get("/rates/lookup")
async def lookup_fx_rate(
    db: DbSession,
    tenant_id: TenantId,
    from_currency: str = Query(..., min_length=3, max_length=3),
    to_currency: str = Query(..., min_length=3, max_length=3),
    on_date: date = Query(...),
) -> dict[str, str]:
    try:
        rate = await get_rate(
            db,
            from_currency=from_currency,
            to_currency=to_currency,
            on_date=on_date,
        )
    except FxRateNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return {
        "from_currency": from_currency.upper(),
        "to_currency": to_currency.upper(),
        "on_date": str(on_date),
        "rate": str(rate),
    }


@router.get("/rates/at")
async def lookup_fx_rate_at(
    db: DbSession,
    tenant_id: TenantId,
    pair: str = Query(..., description="Currency pair as FROM/TO, e.g. GBP/USD"),
    at: datetime = Query(..., description="ISO-8601 timestamp to resolve rate at"),
) -> dict[str, object]:
    """Return the FX rate effective at a specific timestamp, with source and staleness."""
    parts = pair.strip().upper().split("/")
    if len(parts) != 2 or len(parts[0]) != 3 or len(parts[1]) != 3:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="pair must be in FROM/TO format, e.g. GBP/USD",
        )
    from_currency, to_currency = parts

    # Ensure the timestamp is timezone-aware
    if at.tzinfo is None:
        at = at.replace(tzinfo=UTC)

    try:
        result = await get_rate_at(
            db,
            from_currency=from_currency,
            to_currency=to_currency,
            at_datetime=at,
        )
    except FxRateNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return {
        "from_currency": from_currency,
        "to_currency": to_currency,
        "at": at.isoformat(),
        "rate": str(result["rate"]),
        "source": result["source"],
        "rate_timestamp": (
            result["rate_timestamp"].isoformat() if result["rate_timestamp"] else None
        ),
        "staleness_seconds": result["staleness_seconds"],
        "bid_rate": str(result["bid_rate"]) if result.get("bid_rate") is not None else None,
        "ask_rate": str(result["ask_rate"]) if result.get("ask_rate") is not None else None,
    }
