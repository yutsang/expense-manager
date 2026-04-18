"""FX Rates API — upsert, list, lookup, and timestamped rate resolution."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

from fastapi import APIRouter, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from app.api.v1.deps import ActorId, DbSession, TenantId
from app.api.v1.schemas import CsvImportResult, FxRateResponse, FxRateUpsert
from app.infra.models import FxRate
from app.services.csv_import import generate_template_csv, parse_csv, parse_date, parse_decimal
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


# ── CSV Import / Template ────────────────────────────────────────────────────

_FX_REQUIRED = ["from_currency", "to_currency", "rate_date", "rate"]
_FX_OPTIONAL = ["source"]
_FX_ALL = _FX_REQUIRED + _FX_OPTIONAL
_FX_EXAMPLE = ["USD", "EUR", "2025-01-15", "0.9200", "ecb"]


@router.get("/csv-template")
async def csv_template() -> StreamingResponse:
    """Download a CSV template for FX rate imports."""
    content = generate_template_csv(_FX_ALL, _FX_EXAMPLE)
    return StreamingResponse(
        iter([content]),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="fx-rates-template.csv"'},
    )


@router.post("/import", response_model=CsvImportResult, status_code=status.HTTP_201_CREATED)
async def import_fx_rates(
    file: UploadFile,
    db: DbSession,
    tenant_id: TenantId,
    actor_id: ActorId,
) -> CsvImportResult:
    """Import FX rates from a CSV file."""
    content = await file.read()
    rows, errors = await parse_csv(content, _FX_REQUIRED, _FX_OPTIONAL)

    imported = 0
    skipped = 0

    for row_no, row in enumerate(rows, start=2 + len(errors)):
        try:
            from_ccy = row["from_currency"].upper().strip()
            to_ccy = row["to_currency"].upper().strip()

            if len(from_ccy) != 3 or len(to_ccy) != 3:
                errors.append(
                    f"Row {row_no}: currency codes must be 3 characters"
                )
                skipped += 1
                continue

            rate_date = parse_date(row["rate_date"])
            rate = parse_decimal(row["rate"])
            source = row.get("source") or "csv_import"

            await upsert_rate(
                db,
                from_currency=from_ccy,
                to_currency=to_ccy,
                rate_date=rate_date,
                rate=rate,
                source=source,
                force=True,
            )
            imported += 1
        except FxRateSanityError as exc:
            errors.append(f"Row {row_no}: {exc}")
            skipped += 1
        except Exception as exc:
            errors.append(f"Row {row_no}: {exc}")
            skipped += 1

    if imported > 0:
        await db.commit()

    from app.core.logging import get_logger
    get_logger(__name__).info(
        "fx.import.complete",
        tenant_id=tenant_id,
        imported=imported,
        skipped=skipped,
        errors=len(errors),
    )
    return CsvImportResult(imported=imported, skipped=skipped, errors=errors)
