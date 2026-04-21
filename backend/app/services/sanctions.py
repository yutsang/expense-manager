"""Sanctions screening service — OFAC Consolidated + FATF jurisdictions.

Performance note: screen_contact does a full table scan of sanctions_list_entries
for OFAC name matching (O(contacts × entries), ~13k entries in OFAC). This is
acceptable for MVP with a small-to-medium contact list screened in a daily batch
job. For production scale, add pg_trgm indexes and pre-computed name vectors.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json as _json
import os
import xml.etree.ElementTree as ET  # noqa: S405 — parsing trusted government XML, not user input
from datetime import UTC, datetime
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
_UN_URL = "https://scsanctions.un.org/resources/xml/en/consolidated.xml"
_UK_OFSI_URL = "https://ofsistorage.blob.core.windows.net/publishlive/2022format/ConList.csv"
_EU_URL = "https://webgate.ec.europa.eu/fsd/fsf/public/files/xmlFullSanctionsList_1_1/content"
_EU_URL_FALLBACK = "https://webgate.ec.europa.eu/fsd/fsf/public/files/xmlFullSanctionsList/content"
_OPENSANCTIONS_PEP_URL = "https://data.opensanctions.org/datasets/latest/peps/entities.ftm.json"
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
    root = ET.fromstring(xml_bytes.decode("utf-8", errors="replace"))  # noqa: S314  # nosec B314
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

        countries = list({c.text.strip() for c in sdn.findall(".//address/country") if c.text})
        programs = [p.text for p in sdn.findall(".//program") if p.text]
        remarks = sdn.findtext("remarksField")

        entries.append(
            {
                "ref_id": uid,
                "entity_type": sdn_type,
                "primary_name": primary_name,
                "aliases": aliases,
                "countries": countries,
                "programs": programs,
                "remarks": remarks,
                "source": "ofac_consolidated",
            }
        )
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


async def _get_previous_snapshot(db: AsyncSession, source: str) -> SanctionsListSnapshot | None:
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
        fetched_at=datetime.now(tz=UTC),
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
        batch.append(
            SanctionsListEntry(
                snapshot_id=snapshot.id,
                ref_id=e["ref_id"],
                entity_type=e["entity_type"],
                primary_name=e["primary_name"],
                aliases=e.get("aliases", []),
                countries=e.get("countries", []),
                programs=e.get("programs", []),
                remarks=e.get("remarks"),
                source=e["source"],
            )
        )
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


def _strip_ns(tag: str) -> str:
    """Strip XML namespace prefix from a tag, e.g. '{ns}foo' → 'foo'."""
    return tag.split("}")[-1] if "}" in tag else tag


async def _fetch_un_xml() -> bytes:
    async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
        resp = await client.get(_UN_URL)
        resp.raise_for_status()
        return resp.content


def _parse_un_xml(xml_bytes: bytes) -> list[dict[str, Any]]:
    root = ET.fromstring(xml_bytes.decode("utf-8", errors="replace"))  # noqa: S314  # nosec B314
    entries: list[dict[str, Any]] = []

    def _text(el: ET.Element, tag: str) -> str:
        child = el.find(tag)
        if child is None:
            # Try stripping namespace from children
            for c in el:
                if _strip_ns(c.tag) == tag:
                    return (c.text or "").strip()
            return ""
        return (child.text or "").strip()

    def _find_all_stripped(el: ET.Element, tag: str) -> list[ET.Element]:
        return [c for c in el.iter() if _strip_ns(c.tag) == tag]

    for individual in _find_all_stripped(root, "INDIVIDUAL"):
        ref_id = _text(individual, "DATAID")
        if not ref_id:
            continue
        parts = [
            _text(individual, "FIRST_NAME"),
            _text(individual, "SECOND_NAME"),
            _text(individual, "THIRD_NAME"),
            _text(individual, "FOURTH_NAME"),
        ]
        primary_name = " ".join(p for p in parts if p).strip()
        if not primary_name:
            primary_name = ref_id

        aliases: list[dict[str, str]] = []
        for alias_el in _find_all_stripped(individual, "INDIVIDUAL_ALIAS"):
            quality = _text(alias_el, "QUALITY")
            if quality == "Low":
                continue
            alias_name = _text(alias_el, "ALIAS_NAME")
            if alias_name:
                aliases.append({"type": "a.k.a.", "name": alias_name})

        countries: list[str] = []
        for nat_el in _find_all_stripped(individual, "NATIONALITY"):
            val = _text(nat_el, "VALUE")
            if val:
                countries.append(val)
        for addr_el in _find_all_stripped(individual, "INDIVIDUAL_ADDRESS"):
            cid = _text(addr_el, "COUNTRY_ID")
            if cid:
                countries.append(cid)
        countries = list(dict.fromkeys(countries))  # deduplicate, preserve order

        list_type = _text(individual, "UN_LIST_TYPE")
        listed_on = _text(individual, "LISTED_ON")
        programs = [f"{list_type} {listed_on}".strip()] if (list_type or listed_on) else []
        remarks = _text(individual, "COMMENTS1") or None

        entries.append(
            {
                "ref_id": ref_id,
                "entity_type": "individual",
                "primary_name": primary_name,
                "aliases": aliases,
                "countries": countries,
                "programs": programs,
                "remarks": remarks,
                "source": "un_consolidated",
            }
        )

    for entity in _find_all_stripped(root, "ENTITY"):
        ref_id = _text(entity, "DATAID")
        if not ref_id:
            continue
        primary_name = _text(entity, "FIRST_NAME") or ref_id

        aliases = []
        for alias_el in _find_all_stripped(entity, "ENTITY_ALIAS"):
            alias_name = _text(alias_el, "ALIAS_NAME")
            if alias_name:
                aliases.append({"type": "a.k.a.", "name": alias_name})

        countries = []
        for addr_el in _find_all_stripped(entity, "ENTITY_ADDRESS"):
            cid = _text(addr_el, "COUNTRY_ID")
            if cid:
                countries.append(cid)
        countries = list(dict.fromkeys(countries))

        list_type = _text(entity, "UN_LIST_TYPE")
        programs = [list_type] if list_type else []
        remarks = _text(entity, "COMMENTS1") or None

        entries.append(
            {
                "ref_id": ref_id,
                "entity_type": "entity",
                "primary_name": primary_name,
                "aliases": aliases,
                "countries": countries,
                "programs": programs,
                "remarks": remarks,
                "source": "un_consolidated",
            }
        )

    return entries


async def _fetch_and_parse_un() -> tuple[list[dict[str, Any]], str]:
    xml_bytes = await _fetch_un_xml()
    raw_hash = _sha256(xml_bytes)
    return _parse_un_xml(xml_bytes), raw_hash


async def _fetch_uk_ofsi_csv() -> bytes:
    async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
        resp = await client.get(_UK_OFSI_URL)
        resp.raise_for_status()
        return resp.content


def _parse_uk_ofsi_csv(raw_bytes: bytes) -> list[dict[str, Any]]:
    # Try UTF-8 first, fall back to latin-1
    try:
        text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError:
        text = raw_bytes.decode("latin-1")

    reader = csv.DictReader(io.StringIO(text))

    # Group rows by GroupID
    groups: dict[str, dict[str, Any]] = {}
    for row in reader:
        group_id = (row.get("GroupID") or "").strip()
        if not group_id:
            continue

        name_parts = [(row.get(f"Name {i}") or "").strip() for i in range(1, 7)]
        full_name = " ".join(p for p in name_parts if p).strip()
        country = (row.get("Country") or "").strip()
        group_type = (row.get("GroupTypeDescription") or "").strip()

        if group_id not in groups:
            groups[group_id] = {
                "ref_id": group_id,
                "entity_type": "individual" if "individual" in group_type.lower() else "entity",
                "primary_name": full_name,
                "all_names": set(),
                "countries": set(),
                "programs": ["UK_OFSI"],
            }

        if full_name:
            groups[group_id]["all_names"].add(full_name)
        if country:
            groups[group_id]["countries"].add(country)

    entries: list[dict[str, Any]] = []
    for g in groups.values():
        all_names: set[str] = g["all_names"]
        primary = g["primary_name"]
        aliases = [{"type": "a.k.a.", "name": n} for n in sorted(all_names) if n != primary]
        entries.append(
            {
                "ref_id": g["ref_id"],
                "entity_type": g["entity_type"],
                "primary_name": primary,
                "aliases": aliases,
                "countries": sorted(g["countries"]),
                "programs": g["programs"],
                "remarks": None,
                "source": "uk_ofsi",
            }
        )

    return entries


async def _fetch_and_parse_uk_ofsi() -> tuple[list[dict[str, Any]], str]:
    raw_bytes = await _fetch_uk_ofsi_csv()
    raw_hash = _sha256(raw_bytes)
    return _parse_uk_ofsi_csv(raw_bytes), raw_hash


async def _fetch_eu_xml() -> bytes:
    async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
        try:
            resp = await client.get(_EU_URL)
            resp.raise_for_status()
            return resp.content
        except (httpx.HTTPStatusError, httpx.RequestError):
            resp = await client.get(_EU_URL_FALLBACK)
            resp.raise_for_status()
            return resp.content


def _parse_eu_xml(xml_bytes: bytes) -> list[dict[str, Any]]:
    root = ET.fromstring(xml_bytes.decode("utf-8", errors="replace"))  # noqa: S314  # nosec B314
    entries: list[dict[str, Any]] = []

    _EU_TYPE_MAP = {"P": "individual", "E": "entity", "V": "vessel", "A": "aircraft"}

    def _find_stripped(el: ET.Element, tag: str) -> list[ET.Element]:
        return [c for c in el.iter() if _strip_ns(c.tag) == tag]

    def _text_stripped(el: ET.Element, tag: str) -> str:
        for c in el:
            if _strip_ns(c.tag) == tag:
                return (c.text or "").strip()
        return ""

    for entity in _find_stripped(root, "sanctionEntity"):
        ref_id = entity.get("logicalId") or ""
        if not ref_id:
            continue

        # entity_type from subjectType/classificationCode
        entity_type = "entity"
        for st in _find_stripped(entity, "subjectType"):
            code = _text_stripped(st, "classificationCode")
            if not code:
                # classificationCode may be an attribute or direct text
                for cc in st:
                    if _strip_ns(cc.tag) == "classificationCode":
                        code = (cc.text or "").strip()
            entity_type = _EU_TYPE_MAP.get(code, code.lower() if code else "entity")
            break

        # primary_name from first nameAlias with strong="true", else first nameAlias
        name_aliases = _find_stripped(entity, "nameAlias")
        primary_name = ""
        remaining_aliases: list[ET.Element] = []
        strong_found = False
        for na in name_aliases:
            whole_name = (na.get("wholeName") or "").strip()
            if not whole_name:
                fn = (na.get("firstName") or "").strip()
                ln = (na.get("lastName") or "").strip()
                whole_name = f"{fn} {ln}".strip()
            if not strong_found and na.get("strong") == "true":
                primary_name = whole_name
                strong_found = True
            else:
                remaining_aliases.append((na, whole_name))

        if not primary_name and name_aliases:
            first_na = name_aliases[0]
            whole_name = (first_na.get("wholeName") or "").strip()
            if not whole_name:
                fn = (first_na.get("firstName") or "").strip()
                ln = (first_na.get("lastName") or "").strip()
                whole_name = f"{fn} {ln}".strip()
            primary_name = whole_name
            remaining_aliases = [
                (
                    na,
                    (
                        na.get("wholeName") or f"{na.get('firstName', '')} {na.get('lastName', '')}"
                    ).strip(),
                )
                for na in name_aliases[1:]
            ]

        if not primary_name:
            primary_name = ref_id

        aliases = [{"type": "a.k.a.", "name": name} for _, name in remaining_aliases if name]

        # countries from citizenship and address
        countries: list[str] = []
        for cit in _find_stripped(entity, "citizenship"):
            iso = (cit.get("countryIso2Code") or "").strip()
            if not iso:
                for c in cit:
                    if _strip_ns(c.tag) == "countryIso2Code":
                        iso = (c.text or "").strip()
            if iso:
                countries.append(iso)
        for addr in _find_stripped(entity, "address"):
            iso = (addr.get("countryIso2Code") or "").strip()
            if not iso:
                for c in addr:
                    if _strip_ns(c.tag) == "countryIso2Code":
                        iso = (c.text or "").strip()
            if iso:
                countries.append(iso)
        countries = list(dict.fromkeys(countries))

        # programs from regulation/programme
        programs: list[str] = []
        for reg in _find_stripped(entity, "regulation"):
            for prog in _find_stripped(reg, "programme"):
                val = (prog.text or "").strip()
                if val:
                    programs.append(val)

        # remarks
        remarks: str | None = None
        for rem in _find_stripped(entity, "remark"):
            remarks = (rem.text or "").strip() or None
            break

        entries.append(
            {
                "ref_id": ref_id,
                "entity_type": entity_type,
                "primary_name": primary_name,
                "aliases": aliases,
                "countries": countries,
                "programs": programs,
                "remarks": remarks,
                "source": "eu_consolidated",
            }
        )

    return entries


async def _fetch_and_parse_eu() -> tuple[list[dict[str, Any]], str]:
    xml_bytes = await _fetch_eu_xml()
    raw_hash = _sha256(xml_bytes)
    return _parse_eu_xml(xml_bytes), raw_hash


# ── OpenSanctions PEP list ─────────────────────────────────────────────────


async def _fetch_opensanctions_pep_json() -> bytes:
    async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
        resp = await client.get(_OPENSANCTIONS_PEP_URL)
        resp.raise_for_status()
        return resp.content


def _parse_opensanctions_pep_json(raw_bytes: bytes) -> list[dict[str, Any]]:
    """Parse the OpenSanctions PEP JSON feed (FtM entities format).

    Expected structure:
        {"datasets": {...}, "entities": [{"id": ..., "caption": ..., "schema": ...,
         "properties": {"name": [...], "alias": [...], ...}}, ...]}
    """
    data = _json.loads(raw_bytes)
    entities: list[dict[str, Any]] = data.get("entities", [])
    entries: list[dict[str, Any]] = []

    for entity in entities:
        props = entity.get("properties", {})
        names: list[str] = props.get("name", [])
        caption: str = (entity.get("caption") or "").strip()

        # Determine primary name: first entry in name list, else caption
        primary_name = names[0].strip() if names else caption
        if not primary_name:
            continue

        aliases_raw: list[str] = props.get("alias", [])
        aliases = [{"type": "a.k.a.", "name": a} for a in aliases_raw if a]
        countries: list[str] = props.get("country", [])
        positions: list[str] = props.get("position", [])
        notes_list: list[str] = props.get("notes", [])
        remarks: str | None = notes_list[0] if notes_list else None

        entries.append(
            {
                "ref_id": entity.get("id", ""),
                "entity_type": "individual",
                "primary_name": primary_name,
                "aliases": aliases,
                "countries": countries,
                "programs": positions,
                "remarks": remarks,
                "source": "opensanctions_pep",
            }
        )

    return entries


async def _fetch_and_parse_opensanctions_pep() -> tuple[list[dict[str, Any]], str]:
    raw_bytes = await _fetch_opensanctions_pep_json()
    raw_hash = _sha256(raw_bytes)
    return _parse_opensanctions_pep_json(raw_bytes), raw_hash


async def refresh_pep(db: AsyncSession) -> tuple[SanctionsListSnapshot, bool]:
    """Fetch OpenSanctions PEP list, store snapshot, return (snapshot, changed)."""
    raw_bytes = await _fetch_opensanctions_pep_json()
    raw_hash = _sha256(raw_bytes)
    entries = _parse_opensanctions_pep_json(raw_bytes)
    return await _store_snapshot(db, "opensanctions_pep", entries, raw_hash)


async def refresh_additional_lists(db: AsyncSession) -> list[tuple[str, bool]]:
    """Fetch UN, UK OFSI, EU, and PEP lists. Returns list of (source, changed) tuples.

    PEP is gated by SANCTIONS_SKIP_PEP env var because the OpenSanctions PEP
    feed is a ~500MB JSON blob that OOMs constrained containers.
    """
    sources: list[tuple[Any, str]] = [
        (_fetch_and_parse_un, "un_consolidated"),
        (_fetch_and_parse_uk_ofsi, "uk_ofsi"),
        (_fetch_and_parse_eu, "eu_consolidated"),
    ]
    if os.getenv("SANCTIONS_SKIP_PEP", "").lower() not in {"1", "true", "yes"}:
        sources.append((_fetch_and_parse_opensanctions_pep, "opensanctions_pep"))
    else:
        log.info("sanctions.pep_skipped", reason="SANCTIONS_SKIP_PEP")

    results = []
    for fetch_fn, source_name in sources:
        try:
            entries, raw_hash = await fetch_fn()
            snap, changed = await _store_snapshot(db, source_name, entries, raw_hash)
            results.append((source_name, changed))
            log.info(
                "sanctions.list_refreshed", source=source_name, changed=changed, count=len(entries)
            )
        except Exception as exc:
            log.error("sanctions.list_refresh_failed", source=source_name, error=str(exc))
            results.append((source_name, False))
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
        kyc.sanctions_checked_at = datetime.now(tz=UTC)
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
    now = datetime.now(tz=UTC)
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
