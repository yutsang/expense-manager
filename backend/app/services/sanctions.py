"""Sanctions screening service — OFAC Consolidated + FATF jurisdictions.

Performance note: screen_contact does a full table scan of sanctions_list_entries
for OFAC name matching (O(contacts × entries), ~13k entries in OFAC). This is
acceptable for MVP with a small-to-medium contact list screened in a daily batch
job. For production scale, add pg_trgm indexes and pre-computed name vectors.
"""
from __future__ import annotations

import hashlib
import xml.etree.ElementTree as ET  # noqa: S405 — parsing trusted OFAC XML, not user input
from datetime import datetime, timezone
from typing import Any

import httpx
from rapidfuzz import fuzz
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.infra.models import (
    Contact,
    ContactKyc,
    ContactSanctionsResult,
    SanctionsListEntry,
    SanctionsListSnapshot,
)

log = get_logger(__name__)

_OFAC_URL = "https://www.treasury.gov/ofac/downloads/consolidated/consolidated.xml"
_POTENTIAL_MATCH_THRESHOLD = 80
_CONFIRMED_MATCH_THRESHOLD = 95

# ── FATF hardcoded lists (April 2026) ────────────────────────────────────────
# Source: https://www.fatf-gafi.org/en/topics/high-risk-and-other-monitored-jurisdictions.html
_FATF_BLACKLIST: list[dict[str, str]] = [
    {"ref_id": "KP", "primary_name": "North Korea (DPRK)"},
    {"ref_id": "IR", "primary_name": "Iran"},
    {"ref_id": "MM", "primary_name": "Myanmar"},
]
_FATF_GREYLIST: list[dict[str, str]] = [
    {"ref_id": "BG", "primary_name": "Bulgaria"},
    {"ref_id": "BF", "primary_name": "Burkina Faso"},
    {"ref_id": "CM", "primary_name": "Cameroon"},
    {"ref_id": "CI", "primary_name": "Côte d'Ivoire"},
    {"ref_id": "HR", "primary_name": "Croatia"},
    {"ref_id": "CD", "primary_name": "Democratic Republic of Congo"},
    {"ref_id": "HT", "primary_name": "Haiti"},
    {"ref_id": "JM", "primary_name": "Jamaica"},
    {"ref_id": "KE", "primary_name": "Kenya"},
    {"ref_id": "ML", "primary_name": "Mali"},
    {"ref_id": "MZ", "primary_name": "Mozambique"},
    {"ref_id": "NA", "primary_name": "Namibia"},
    {"ref_id": "NG", "primary_name": "Nigeria"},
    {"ref_id": "PH", "primary_name": "Philippines"},
    {"ref_id": "SN", "primary_name": "Senegal"},
    {"ref_id": "ZA", "primary_name": "South Africa"},
    {"ref_id": "SS", "primary_name": "South Sudan"},
    {"ref_id": "SY", "primary_name": "Syria"},
    {"ref_id": "TZ", "primary_name": "Tanzania"},
    {"ref_id": "VN", "primary_name": "Vietnam"},
    {"ref_id": "YE", "primary_name": "Yemen"},
    {"ref_id": "TR", "primary_name": "Türkiye"},
    {"ref_id": "AE", "primary_name": "United Arab Emirates"},
]


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


async def _fetch_ofac_xml() -> bytes:
    async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
        resp = await client.get(_OFAC_URL)
        resp.raise_for_status()
        return resp.content


def _parse_ofac_xml(xml_bytes: bytes) -> list[dict[str, Any]]:
    root = ET.fromstring(xml_bytes.decode("utf-8", errors="replace"))  # noqa: S314
    entries: list[dict[str, Any]] = []
    for sdn in root.findall(".//sdnEntry"):
        uid = sdn.findtext("uid") or ""
        first = sdn.findtext("firstName") or ""
        last = sdn.findtext("lastName") or ""
        primary_name = f"{first} {last}".strip() if first else last
        if not primary_name:
            continue
        sdn_type = (sdn.findtext("sdnType") or "Entity").lower().replace(" ", "_")

        aliases: list[dict[str, str]] = []
        for aka in sdn.findall(".//aka"):
            a_first = aka.findtext("firstName") or ""
            a_last = aka.findtext("lastName") or ""
            a_name = f"{a_first} {a_last}".strip() if a_first else a_last
            if a_name:
                aliases.append({"type": aka.findtext("type") or "a.k.a.", "name": a_name})

        countries = list({
            c.text.strip()
            for c in sdn.findall(".//address/country")
            if c.text
        })
        programs = [p.text for p in sdn.findall(".//program") if p.text]
        remarks = sdn.findtext("remarksField")

        entries.append({
            "ref_id": uid,
            "entity_type": sdn_type,
            "primary_name": primary_name,
            "aliases": aliases,
            "countries": countries,
            "programs": programs,
            "remarks": remarks,
            "source": "ofac_consolidated",
        })
    return entries


def _compute_name_score(contact_name: str, entry: SanctionsListEntry) -> tuple[int, str]:
    """Return (best_score 0-100, best_matching_name)."""
    upper = contact_name.upper()
    names: list[str] = [entry.primary_name] + [a["name"] for a in (entry.aliases or [])]
    best_score = 0
    best_name = entry.primary_name
    for name in names:
        score = int(fuzz.WRatio(upper, name.upper()))
        if score > best_score:
            best_score = score
            best_name = name
    return best_score, best_name


async def _get_previous_snapshot(
    db: AsyncSession, source: str
) -> SanctionsListSnapshot | None:
    return await db.scalar(
        select(SanctionsListSnapshot).where(
            SanctionsListSnapshot.source == source,
            SanctionsListSnapshot.is_active.is_(True),
        )
    )


async def _store_snapshot(
    db: AsyncSession,
    source: str,
    entries: list[dict[str, Any]],
    raw_hash: str,
    notes: str | None = None,
) -> tuple[SanctionsListSnapshot, bool]:
    """Store a new snapshot. Returns (snapshot, is_changed)."""
    prev = await _get_previous_snapshot(db, source)
    if prev and prev.sha256_hash == raw_hash:
        log.info("sanctions.snapshot_unchanged", source=source)
        return prev, False

    # Deactivate previous snapshot
    if prev:
        prev.is_active = False

    snapshot = SanctionsListSnapshot(
        source=source,
        fetched_at=datetime.now(tz=timezone.utc),
        entry_count=len(entries),
        sha256_hash=raw_hash,
        is_active=True,
        notes=notes,
    )
    db.add(snapshot)
    await db.flush()  # get snapshot.id

    # Bulk insert entries in batches of 500
    batch: list[SanctionsListEntry] = []
    for e in entries:
        batch.append(SanctionsListEntry(
            snapshot_id=snapshot.id,
            ref_id=e["ref_id"],
            entity_type=e["entity_type"],
            primary_name=e["primary_name"],
            aliases=e.get("aliases", []),
            countries=e.get("countries", []),
            programs=e.get("programs", []),
            remarks=e.get("remarks"),
            source=e["source"],
        ))
        if len(batch) >= 500:
            db.add_all(batch)
            await db.flush()
            batch = []
    if batch:
        db.add_all(batch)
        await db.flush()

    log.info("sanctions.snapshot_stored", source=source, count=len(entries))
    return snapshot, True


async def refresh_ofac(db: AsyncSession) -> tuple[SanctionsListSnapshot, bool]:
    """Fetch OFAC consolidated list, store snapshot, return (snapshot, changed)."""
    xml_bytes = await _fetch_ofac_xml()
    raw_hash = _sha256(xml_bytes)
    entries = _parse_ofac_xml(xml_bytes)
    return await _store_snapshot(db, "ofac_consolidated", entries, raw_hash)


async def refresh_fatf(db: AsyncSession) -> list[tuple[SanctionsListSnapshot, bool]]:
    """Store/refresh FATF blacklist and greylist snapshots."""
    results = []
    for list_name, raw_entries, source in [
        ("blacklist", _FATF_BLACKLIST, "fatf_blacklist"),
        ("greylist", _FATF_GREYLIST, "fatf_greylist"),
    ]:
        entries = [
            {
                "ref_id": e["ref_id"],
                "entity_type": "country",
                "primary_name": e["primary_name"],
                "aliases": [],
                "countries": [e["ref_id"]],
                "programs": [],
                "remarks": None,
                "source": source,
            }
            for e in raw_entries
        ]
        raw_hash = _sha256("|".join(e["ref_id"] for e in entries).encode())
        result = await _store_snapshot(
            db, source, entries, raw_hash, notes=f"FATF {list_name} April 2026"
        )
        results.append(result)
    return results


async def screen_contact(
    db: AsyncSession,
    *,
    contact_id: str,
    tenant_id: str,
    contact_name: str,
    contact_country: str | None = None,
) -> ContactSanctionsResult:
    """Screen a contact against all active sanctions lists, upsert the result."""
    active_snaps_result = await db.execute(
        select(SanctionsListSnapshot.id, SanctionsListSnapshot.source).where(
            SanctionsListSnapshot.is_active.is_(True)
        )
    )
    active_snap_rows = active_snaps_result.all()
    if not active_snap_rows:
        log.info("sanctions.no_active_snapshots", contact_id=contact_id)
        return await _upsert_result(
            db,
            contact_id=contact_id,
            tenant_id=tenant_id,
            match_status="clear",
            match_score=0,
            details=[],
        )

    best_score = 0
    best_match: dict[str, Any] = {}
    all_details: list[dict[str, Any]] = []

    for snap_id, source in active_snap_rows:
        if source in ("fatf_blacklist", "fatf_greylist"):
            # FATF is country-level: check contact country code against ref_id
            if not contact_country:
                continue
            entries_result = await db.execute(
                select(SanctionsListEntry).where(
                    SanctionsListEntry.snapshot_id == snap_id,
                    SanctionsListEntry.ref_id == contact_country.upper(),
                )
            )
            for entry in entries_result.scalars():
                score = 100  # exact country match
                risk = "high" if source == "fatf_blacklist" else "medium"
                detail: dict[str, Any] = {
                    "entry_id": entry.id,
                    "name": entry.primary_name,
                    "score": score,
                    "source": source,
                    "risk": risk,
                }
                all_details.append(detail)
                if score > best_score:
                    best_score = score
                    best_match = {
                        "entry_id": entry.id,
                        "matched_name": entry.primary_name,
                        "snapshot_id": snap_id,
                    }
        else:
            # OFAC: fuzzy name match across all entries in snapshot
            entries_result = await db.execute(
                select(SanctionsListEntry).where(
                    SanctionsListEntry.snapshot_id == snap_id,
                )
            )
            for entry in entries_result.scalars():
                score, matched_name = _compute_name_score(contact_name, entry)
                if score >= _POTENTIAL_MATCH_THRESHOLD:
                    detail = {
                        "entry_id": entry.id,
                        "name": matched_name,
                        "score": score,
                        "source": source,
                    }
                    all_details.append(detail)
                    if score > best_score:
                        best_score = score
                        best_match = {
                            "entry_id": entry.id,
                            "matched_name": matched_name,
                            "snapshot_id": snap_id,
                        }

    if best_score >= _CONFIRMED_MATCH_THRESHOLD:
        match_status = "confirmed_match"
    elif best_score >= _POTENTIAL_MATCH_THRESHOLD:
        match_status = "potential_match"
    else:
        match_status = "clear"

    result = await _upsert_result(
        db,
        contact_id=contact_id,
        tenant_id=tenant_id,
        match_status=match_status,
        match_score=best_score,
        matched_entry_id=best_match.get("entry_id"),
        matched_name=best_match.get("matched_name"),
        snapshot_id=best_match.get("snapshot_id"),
        details=all_details[:20],  # cap at 20 to control storage size
    )

    # Sync back to contact_kyc.sanctions_status
    kyc = await db.scalar(
        select(ContactKyc).where(
            ContactKyc.contact_id == contact_id,
            ContactKyc.tenant_id == tenant_id,
        )
    )
    if kyc:
        if match_status == "confirmed_match":
            kyc.sanctions_status = "flagged"
        elif match_status == "potential_match":
            kyc.sanctions_status = "under_review"
        else:
            kyc.sanctions_status = "clear"
        kyc.sanctions_checked_at = datetime.now(tz=timezone.utc)
        await db.flush()

    return result


async def _upsert_result(
    db: AsyncSession,
    *,
    contact_id: str,
    tenant_id: str,
    match_status: str,
    match_score: int,
    matched_entry_id: str | None = None,
    matched_name: str | None = None,
    snapshot_id: str | None = None,
    details: list[dict[str, Any]] | None = None,
) -> ContactSanctionsResult:
    existing = await db.scalar(
        select(ContactSanctionsResult).where(
            ContactSanctionsResult.contact_id == contact_id,
            ContactSanctionsResult.tenant_id == tenant_id,
        )
    )
    now = datetime.now(tz=timezone.utc)
    if existing:
        existing.screened_at = now
        existing.match_status = match_status
        existing.match_score = match_score
        existing.matched_entry_id = matched_entry_id
        existing.matched_name = matched_name
        existing.snapshot_id = snapshot_id
        existing.details = details or []
        await db.flush()
        return existing
    result = ContactSanctionsResult(
        tenant_id=tenant_id,
        contact_id=contact_id,
        screened_at=now,
        snapshot_id=snapshot_id,
        match_status=match_status,
        match_score=match_score,
        matched_entry_id=matched_entry_id,
        matched_name=matched_name,
        details=details or [],
    )
    db.add(result)
    await db.flush()
    return result


async def screen_all_contacts(db: AsyncSession, *, tenant_id: str) -> dict[str, int]:
    """Screen all non-archived contacts for a tenant. Returns counts by match_status."""
    contacts_result = await db.execute(
        select(Contact.id, Contact.name, Contact.country).where(
            Contact.tenant_id == tenant_id,
            Contact.is_archived.is_(False),
        )
    )
    rows = contacts_result.all()
    counts: dict[str, int] = {"clear": 0, "potential_match": 0, "confirmed_match": 0}
    for contact_id, name, country in rows:
        r = await screen_contact(
            db,
            contact_id=contact_id,
            tenant_id=tenant_id,
            contact_name=name,
            contact_country=country,
        )
        counts[r.match_status] = counts.get(r.match_status, 0) + 1
    return counts


async def get_latest_snapshots(db: AsyncSession) -> list[SanctionsListSnapshot]:
    """Return all currently active sanctions list snapshots."""
    result = await db.execute(
        select(SanctionsListSnapshot).where(SanctionsListSnapshot.is_active.is_(True))
    )
    return list(result.scalars())


async def get_screening_result(
    db: AsyncSession, *, contact_id: str, tenant_id: str
) -> ContactSanctionsResult | None:
    """Return the current screening result for a contact, or None if not screened."""
    return await db.scalar(
        select(ContactSanctionsResult).where(
            ContactSanctionsResult.contact_id == contact_id,
            ContactSanctionsResult.tenant_id == tenant_id,
        )
    )
