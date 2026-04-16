"""FX rate service — lookup, upsert, and daily-sync stub."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.infra.models import FxRate

log = get_logger(__name__)


class FxRateNotFoundError(ValueError):
    pass


async def get_rate(
    db: AsyncSession,
    *,
    from_currency: str,
    to_currency: str,
    on_date: date,
) -> Decimal:
    """Return the FX rate for a currency pair on a given date.

    Falls back to the most recent known rate before the date.
    Returns Decimal("1") for same-currency (USD→USD) pairs.
    """
    if from_currency.upper() == to_currency.upper():
        return Decimal("1")

    result = await db.execute(
        select(FxRate)
        .where(
            FxRate.from_currency == from_currency.upper(),
            FxRate.to_currency == to_currency.upper(),
            FxRate.rate_date <= datetime.combine(on_date, datetime.min.time()).replace(tzinfo=UTC),
        )
        .order_by(FxRate.rate_date.desc())
        .limit(1)
    )
    row = result.scalar_one_or_none()
    if not row:
        raise FxRateNotFoundError(
            f"No FX rate found for {from_currency}→{to_currency} on or before {on_date}"
        )
    return Decimal(str(row.rate))


async def upsert_rate(
    db: AsyncSession,
    *,
    from_currency: str,
    to_currency: str,
    rate_date: date,
    rate: Decimal,
    source: str = "manual",
) -> FxRate:
    """Insert or update an FX rate. Idempotent by (from, to, date)."""
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    stmt = pg_insert(FxRate).values(
        id=str(uuid.uuid4()),
        from_currency=from_currency.upper(),
        to_currency=to_currency.upper(),
        rate_date=datetime.combine(rate_date, datetime.min.time()).replace(tzinfo=UTC),
        rate=rate,
        source=source,
        created_at=datetime.now(tz=UTC),
    )
    stmt = stmt.on_conflict_do_update(
        constraint="uq_fx_rates_pair_date",
        set_={"rate": rate, "source": source},
    )
    await db.execute(stmt)
    await db.flush()

    result = await db.execute(
        select(FxRate).where(
            FxRate.from_currency == from_currency.upper(),
            FxRate.to_currency == to_currency.upper(),
            FxRate.rate_date
            == datetime.combine(rate_date, datetime.min.time()).replace(tzinfo=UTC),
        )
    )
    return result.scalar_one()


async def convert_amount(
    db: AsyncSession,
    *,
    amount: Decimal,
    from_currency: str,
    to_currency: str,
    on_date: date,
) -> tuple[Decimal, Decimal]:
    """Convert amount and return (converted_amount, rate_used)."""
    rate = await get_rate(db, from_currency=from_currency, to_currency=to_currency, on_date=on_date)
    return amount * rate, rate


# ── Stub: daily FX feed sync (real implementation wires to Plaid/ExchangeRate-API) ──

MOCK_RATES: dict[tuple[str, str], Decimal] = {
    ("USD", "AUD"): Decimal("1.53"),
    ("USD", "GBP"): Decimal("0.79"),
    ("USD", "EUR"): Decimal("0.92"),
    ("USD", "HKD"): Decimal("7.79"),
    ("USD", "SGD"): Decimal("1.33"),
    ("USD", "JPY"): Decimal("154.2"),
    ("AUD", "USD"): Decimal("0.65"),
    ("GBP", "USD"): Decimal("1.27"),
    ("EUR", "USD"): Decimal("1.09"),
}


async def sync_daily_rates(db: AsyncSession, *, on_date: date) -> int:
    """Populate FX rates for `on_date` from MOCK_RATES (dev) or real feed (prod)."""
    count = 0
    for (from_c, to_c), rate in MOCK_RATES.items():
        await upsert_rate(
            db,
            from_currency=from_c,
            to_currency=to_c,
            rate_date=on_date,
            rate=rate,
            source="mock_feed",
        )
        count += 1
    log.info("fx_rates_synced", date=str(on_date), count=count)
    return count
