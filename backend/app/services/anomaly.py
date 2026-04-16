"""Anomaly detection service — scans recent journal entries for suspicious patterns.

Detects:
1. Duplicates: same description + same total_debit within 3 days
2. Round numbers: total_debit is an exact multiple of 1000
3. Statistical outliers: total_debit > mean + 3 * stddev
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def scan_anomalies(db: AsyncSession, tenant_id: str) -> list[dict]:
    """Scan last 30 days of posted journal entries for anomalies.

    Returns a list of dicts with keys:
        type, severity, journal_id, journal_number, description, amount,
        detected_at, detail
    """
    cutoff = (datetime.now(tz=timezone.utc) - timedelta(days=30)).date()

    # Fetch all posted journal entries in the window
    rows_result = await db.execute(
        text("""
            SELECT
                id,
                number,
                description,
                total_debit,
                date
            FROM journal_entries
            WHERE tenant_id = :tid
              AND status = 'posted'
              AND date >= :cutoff
            ORDER BY date ASC
        """),
        {"tid": tenant_id, "cutoff": cutoff},
    )
    entries = rows_result.fetchall()

    if not entries:
        return []

    now = datetime.now(tz=timezone.utc).isoformat()
    anomalies: list[dict] = []

    amounts = [Decimal(str(e.total_debit)) for e in entries]

    # --- Statistical outlier baseline (mean + 3*stddev) ---
    n = len(amounts)
    mean = sum(amounts) / n
    if n > 1:
        variance = sum((a - mean) ** 2 for a in amounts) / n
        stddev = Decimal(str(math.sqrt(float(variance))))
        outlier_threshold = mean + 3 * stddev
    else:
        outlier_threshold = None

    # --- Check 1: Duplicates (same description + same total_debit within 3 days) ---
    # Build a list sorted by (description, total_debit, date)
    sorted_entries = sorted(
        entries,
        key=lambda e: (e.description or "", str(e.total_debit), str(e.date)),
    )
    seen_duplicates: set[str] = set()

    for i, entry in enumerate(sorted_entries):
        if entry.id in seen_duplicates:
            continue
        for j in range(i + 1, len(sorted_entries)):
            other = sorted_entries[j]
            if (other.description or "") != (entry.description or ""):
                break  # sorted, so no more matches on description
            if str(other.total_debit) != str(entry.total_debit):
                continue

            # Check date proximity
            def _to_date(v: object) -> datetime:
                from datetime import date as _date
                if isinstance(v, datetime):
                    return v
                if isinstance(v, _date):
                    return datetime(v.year, v.month, v.day, tzinfo=timezone.utc)
                return datetime.fromisoformat(str(v))

            d1 = _to_date(entry.date)
            d2 = _to_date(other.date)
            delta_days = abs((d2 - d1).days)
            if delta_days <= 3:
                seen_duplicates.add(entry.id)
                seen_duplicates.add(other.id)
                anomalies.append({
                    "type": "duplicate",
                    "severity": "high",
                    "journal_id": entry.id,
                    "journal_number": entry.number,
                    "description": entry.description or "",
                    "amount": str(Decimal(str(entry.total_debit))),
                    "detected_at": now,
                    "detail": (
                        f"Possible duplicate of journal {other.number} "
                        f"({delta_days} day(s) apart, same description and amount)"
                    ),
                })

    # --- Check 2: Round numbers (exact multiple of 1000) ---
    for entry in entries:
        amount = Decimal(str(entry.total_debit))
        if amount > Decimal("0") and amount % Decimal("1000") == Decimal("0"):
            anomalies.append({
                "type": "round_number",
                "severity": "low",
                "journal_id": entry.id,
                "journal_number": entry.number,
                "description": entry.description or "",
                "amount": str(amount),
                "detected_at": now,
                "detail": f"Total debit {amount} is an exact multiple of 1000",
            })

    # --- Check 3: Statistical outliers (> mean + 3*stddev) ---
    if outlier_threshold is not None:
        for entry in entries:
            amount = Decimal(str(entry.total_debit))
            if amount > outlier_threshold:
                anomalies.append({
                    "type": "statistical_outlier",
                    "severity": "medium",
                    "journal_id": entry.id,
                    "journal_number": entry.number,
                    "description": entry.description or "",
                    "amount": str(amount),
                    "detected_at": now,
                    "detail": (
                        f"Total debit {amount} exceeds mean + 3σ "
                        f"(mean={mean:.2f}, σ={stddev:.2f}, threshold={outlier_threshold:.2f})"
                    ),
                })

    return anomalies
