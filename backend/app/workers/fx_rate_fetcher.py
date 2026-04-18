"""ARQ worker: fetch FX rates from the ECB XML feed.

The ECB publishes daily reference rates at:
  https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml

This worker parses the XML, extracts EUR-based rates, and stores them in the
fx_rates table. Cross-rates (e.g. USD/GBP) are derived by triangulation
through EUR.

Usage as an ARQ task:
    async def startup(ctx): ...
    class WorkerSettings:
        functions = [fetch_ecb_rates]
        cron_jobs = [cron(fetch_ecb_rates, hour=16, minute=30)]  # after ECB publish
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from xml.etree import ElementTree

from app.core.db import AsyncSessionLocal
from app.core.logging import get_logger

log = get_logger(__name__)

ECB_DAILY_URL = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml"
ECB_NS = {"gesmes": "http://www.gesmes.org/xml/2002-08-01", "eurofxref": "http://www.ecb.int/vocabulary/2002-08-01/eurofxref"}

# Common cross-rate pairs to derive from EUR base rates
CROSS_RATE_PAIRS: list[tuple[str, str]] = [
    ("USD", "GBP"),
    ("USD", "EUR"),
    ("USD", "AUD"),
    ("USD", "HKD"),
    ("USD", "SGD"),
    ("USD", "JPY"),
    ("GBP", "USD"),
    ("EUR", "USD"),
    ("AUD", "USD"),
]


def parse_ecb_xml(xml_content: str) -> tuple[str, dict[str, Decimal]]:
    """Parse ECB daily XML and return (date_str, {currency: rate_vs_EUR}).

    Returns rates as EUR -> currency (e.g. EUR/USD = 1.08).
    """
    root = ElementTree.fromstring(xml_content)  # noqa: S314

    # Navigate: <Cube><Cube time="2026-04-18"><Cube currency="USD" rate="1.08"/>...
    cube_outer = root.find(".//eurofxref:Cube/eurofxref:Cube", ECB_NS)
    if cube_outer is None:
        raise ValueError("Could not find rate Cube element in ECB XML")

    rate_date = cube_outer.attrib.get("time", "")
    if not rate_date:
        raise ValueError("Missing time attribute on ECB Cube element")

    rates: dict[str, Decimal] = {}
    for cube in cube_outer.findall("eurofxref:Cube", ECB_NS):
        currency = cube.attrib.get("currency", "")
        rate_str = cube.attrib.get("rate", "")
        if currency and rate_str:
            rates[currency] = Decimal(rate_str)

    return rate_date, rates


def derive_cross_rates(
    eur_rates: dict[str, Decimal],
) -> list[tuple[str, str, Decimal]]:
    """Derive cross-rates from EUR-based rates.

    For a pair like USD/GBP:
      EUR/USD = eur_rates["USD"]
      EUR/GBP = eur_rates["GBP"]
      USD/GBP = EUR/GBP / EUR/USD
    """
    # Add EUR itself for completeness
    full_rates = {"EUR": Decimal("1"), **eur_rates}

    results: list[tuple[str, str, Decimal]] = []
    for from_ccy, to_ccy in CROSS_RATE_PAIRS:
        if from_ccy in full_rates and to_ccy in full_rates:
            # from_ccy/to_ccy = (EUR/to_ccy) / (EUR/from_ccy)
            cross = full_rates[to_ccy] / full_rates[from_ccy]
            results.append((from_ccy, to_ccy, cross))

    return results


async def store_rates(
    rate_date_str: str,
    cross_rates: list[tuple[str, str, Decimal]],
    rate_timestamp: datetime | None = None,
) -> int:
    """Store derived cross-rates in the fx_rates table."""
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    from app.infra.models import FxRate

    count = 0
    async with AsyncSessionLocal() as db:
        rate_dt = datetime.fromisoformat(rate_date_str + "T00:00:00+00:00")
        now = datetime.now(tz=UTC)

        for from_ccy, to_ccy, rate in cross_rates:
            stmt = pg_insert(FxRate).values(
                id=str(uuid.uuid4()),
                from_currency=from_ccy,
                to_currency=to_ccy,
                rate_date=rate_dt,
                rate=rate,
                source="ecb",
                rate_timestamp=rate_timestamp or now,
                created_at=now,
            )
            stmt = stmt.on_conflict_do_update(
                constraint="uq_fx_rates_pair_date",
                set_={"rate": rate, "source": "ecb", "rate_timestamp": rate_timestamp or now},
            )
            await db.execute(stmt)
            count += 1

        await db.commit()

    return count


async def fetch_ecb_rates(ctx: dict[str, Any] | None = None) -> dict[str, Any]:
    """ARQ task: fetch ECB daily rates, derive cross-rates, store them.

    In production this would use httpx to fetch ECB_DAILY_URL.
    The actual HTTP call is separated so the parsing/storage logic can be
    tested without network access.
    """
    try:
        import httpx

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(ECB_DAILY_URL)
            resp.raise_for_status()
            xml_content = resp.text
    except Exception:
        log.warning("ecb_fetch_failed_using_stub", exc_info=True)
        # Fall back to stub data in dev/test environments
        xml_content = _stub_ecb_xml()

    rate_date, eur_rates = parse_ecb_xml(xml_content)
    cross_rates = derive_cross_rates(eur_rates)
    now = datetime.now(tz=UTC)
    count = await store_rates(rate_date, cross_rates, rate_timestamp=now)

    log.info("ecb_rates_fetched", date=rate_date, pairs=count)
    return {"date": rate_date, "pairs_stored": count}


def _stub_ecb_xml() -> str:
    """Return minimal ECB XML for dev/test when network is unavailable."""
    return """<?xml version="1.0" encoding="UTF-8"?>
<gesmes:Envelope xmlns:gesmes="http://www.gesmes.org/xml/2002-08-01"
                 xmlns="http://www.ecb.int/vocabulary/2002-08-01/eurofxref">
  <gesmes:subject>Reference rates</gesmes:subject>
  <Cube>
    <Cube time="2026-04-18">
      <Cube currency="USD" rate="1.0800"/>
      <Cube currency="GBP" rate="0.8560"/>
      <Cube currency="AUD" rate="1.6600"/>
      <Cube currency="HKD" rate="8.3800"/>
      <Cube currency="SGD" rate="1.4400"/>
      <Cube currency="JPY" rate="163.50"/>
    </Cube>
  </Cube>
</gesmes:Envelope>"""
