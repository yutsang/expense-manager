"""Unit tests for the OpenSanctions Default (consolidated) feed integration.

Covers:
  * ``_OPENSANCTIONS_DEFAULT_URL`` constant
  * ``_parse_opensanctions_default_line`` — FtM NDJSON → canonical entry dict
  * Streaming fetch & hashing (line boundaries across chunks, unicode)
  * ``SANCTIONS_SKIP_OPENSANCTIONS_DEFAULT`` env gate inside
    ``refresh_additional_lists``
  * Fuzzy scorer upgrade: exact-match fast-path + ``fuzz.token_set_ratio``
  * End-to-end ``screen_contact`` flow with the Carrie Lam alias case
  * Audit event emitted on changed snapshots only
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import AsyncIterator, Generator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import sqlalchemy as sa
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

FIXTURES = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# 1.  _OPENSANCTIONS_DEFAULT_URL
# ---------------------------------------------------------------------------


class TestOpenSanctionsDefaultUrl:
    def test_url_points_to_opensanctions_dataset(self) -> None:
        from app.services.sanctions import _OPENSANCTIONS_DEFAULT_URL

        # We use the focused `sanctions` dataset, not `default` — see the
        # comment on the constant for why.
        assert "opensanctions.org" in _OPENSANCTIONS_DEFAULT_URL
        assert "/sanctions/" in _OPENSANCTIONS_DEFAULT_URL
        assert _OPENSANCTIONS_DEFAULT_URL.endswith(".ftm.json")


# ---------------------------------------------------------------------------
# 2.  _parse_opensanctions_default_line
# ---------------------------------------------------------------------------


class TestParseOpenSanctionsDefaultLine:
    def test_parses_person_with_aliases_and_countries(self) -> None:
        from app.services.sanctions import _parse_opensanctions_default_line

        line = json.dumps(
            {
                "id": "ofac-lam",
                "caption": "LAM, Cheng Yuet-Ngor",
                "schema": "Person",
                "properties": {
                    "name": ["LAM, Cheng Yuet-Ngor"],
                    "alias": ["LAM, Carrie", "Carrie Lam"],
                    "country": ["hk"],
                    "topics": ["sanction", "role.pep"],
                    "notes": ["Former CE of Hong Kong"],
                },
            }
        ).encode()

        entry = _parse_opensanctions_default_line(line)

        assert entry is not None
        assert entry["ref_id"] == "ofac-lam"
        assert entry["primary_name"] == "LAM, Cheng Yuet-Ngor"
        assert entry["entity_type"] == "individual"
        assert entry["source"] == "opensanctions_default"
        assert {"type": "a.k.a.", "name": "LAM, Carrie"} in entry["aliases"]
        assert {"type": "a.k.a.", "name": "Carrie Lam"} in entry["aliases"]
        assert entry["countries"] == ["hk"]
        assert entry["programs"] == ["sanction", "role.pep"]
        assert entry["remarks"] == "Former CE of Hong Kong"

    def test_returns_none_for_empty_line(self) -> None:
        from app.services.sanctions import _parse_opensanctions_default_line

        assert _parse_opensanctions_default_line(b"") is None
        assert _parse_opensanctions_default_line(b"   \t  ") is None

    def test_returns_none_for_malformed_json(self) -> None:
        from app.services.sanctions import _parse_opensanctions_default_line

        assert _parse_opensanctions_default_line(b"{broken json") is None

    def test_returns_none_when_no_name_or_caption(self) -> None:
        from app.services.sanctions import _parse_opensanctions_default_line

        line = json.dumps({"id": "nameless", "schema": "Person", "properties": {}}).encode()
        assert _parse_opensanctions_default_line(line) is None

    @pytest.mark.parametrize(
        ("schema", "expected"),
        [
            ("Person", "individual"),
            ("Organization", "organization"),
            ("Company", "organization"),
            ("LegalEntity", "organization"),
            ("Vessel", "vessel"),
            ("Airplane", "aircraft"),
        ],
    )
    def test_schema_mapped_to_entity_type(self, schema: str, expected: str) -> None:
        from app.services.sanctions import _parse_opensanctions_default_line

        line = json.dumps(
            {
                "id": f"ent-{schema}",
                "caption": f"Example {schema}",
                "schema": schema,
                "properties": {"name": [f"Example {schema}"]},
            }
        ).encode()
        entry = _parse_opensanctions_default_line(line)
        assert entry is not None
        assert entry["entity_type"] == expected

    def test_caption_fallback_when_name_list_empty(self) -> None:
        from app.services.sanctions import _parse_opensanctions_default_line

        line = json.dumps(
            {
                "id": "x",
                "caption": "Fallback",
                "schema": "Person",
                "properties": {"name": []},
            }
        ).encode()
        entry = _parse_opensanctions_default_line(line)
        assert entry is not None
        assert entry["primary_name"] == "Fallback"

    def test_missing_optional_fields(self) -> None:
        from app.services.sanctions import _parse_opensanctions_default_line

        line = json.dumps(
            {
                "id": "x",
                "caption": "Minimal",
                "schema": "Person",
                "properties": {"name": ["Minimal"]},
            }
        ).encode()
        entry = _parse_opensanctions_default_line(line)
        assert entry is not None
        assert entry["aliases"] == []
        assert entry["countries"] == []
        assert entry["programs"] == []
        assert entry["remarks"] is None


# ---------------------------------------------------------------------------
# 3.  Streaming fetch (_fetch_and_parse_opensanctions_default)
# ---------------------------------------------------------------------------


def _make_ndjson_bytes(entities: list[dict[str, Any]]) -> bytes:
    return b"\n".join(json.dumps(e).encode() for e in entities) + b"\n"


class _FakeStreamResponse:
    def __init__(self, chunks: list[bytes]) -> None:
        self._chunks = chunks

    def raise_for_status(self) -> None:
        return None

    async def aiter_bytes(self, chunk_size: int = 65536) -> AsyncIterator[bytes]:
        for c in self._chunks:
            yield c

    async def __aenter__(self) -> _FakeStreamResponse:
        return self

    async def __aexit__(self, *args: Any) -> None:
        return None


class _FakeAsyncClient:
    """Stand-in for ``httpx.AsyncClient`` exposing ``stream``."""

    def __init__(self, chunks: list[bytes]) -> None:
        self._chunks = chunks

    async def __aenter__(self) -> _FakeAsyncClient:
        return self

    async def __aexit__(self, *args: Any) -> None:
        return None

    def stream(self, method: str, url: str) -> _FakeStreamResponse:
        return _FakeStreamResponse(self._chunks)


class TestFetchAndParseOpenSanctionsDefault:
    @pytest.mark.anyio
    async def test_returns_entries_and_matching_sha256(self) -> None:
        from app.services.sanctions import _fetch_and_parse_opensanctions_default

        entities = [
            {
                "id": "a",
                "caption": "Alice",
                "schema": "Person",
                "properties": {"name": ["Alice"]},
            },
            {
                "id": "b",
                "caption": "Bob",
                "schema": "Person",
                "properties": {"name": ["Bob"]},
            },
        ]
        payload = _make_ndjson_bytes(entities)
        expected_hash = hashlib.sha256(payload).hexdigest()

        def factory() -> _FakeAsyncClient:
            # feed the payload in one chunk
            return _FakeAsyncClient([payload])

        entries, raw_hash = await _fetch_and_parse_opensanctions_default(client_factory=factory)
        assert raw_hash == expected_hash
        assert len(entries) == 2
        assert entries[0]["ref_id"] == "a"
        assert entries[1]["ref_id"] == "b"

    @pytest.mark.anyio
    async def test_handles_line_boundary_split_across_chunks(self) -> None:
        from app.services.sanctions import _fetch_and_parse_opensanctions_default

        entities = [
            {
                "id": f"id-{i}",
                "caption": f"Entity {i}",
                "schema": "Person",
                "properties": {"name": [f"Entity {i}"]},
            }
            for i in range(5)
        ]
        payload = _make_ndjson_bytes(entities)
        # split payload at an arbitrary byte boundary so newlines straddle chunks
        mid = len(payload) // 2
        chunks = [payload[:mid], payload[mid:]]
        expected_hash = hashlib.sha256(payload).hexdigest()

        entries, raw_hash = await _fetch_and_parse_opensanctions_default(
            client_factory=lambda: _FakeAsyncClient(chunks)
        )
        assert raw_hash == expected_hash
        assert len(entries) == 5
        assert [e["ref_id"] for e in entries] == [f"id-{i}" for i in range(5)]

    @pytest.mark.anyio
    async def test_unicode_roundtrip(self) -> None:
        from app.services.sanctions import _fetch_and_parse_opensanctions_default

        entities = [
            {
                "id": "u1",
                "caption": "张三",
                "schema": "Person",
                "properties": {"name": ["张三"], "alias": ["Zhāng Sān"]},
            }
        ]
        payload = _make_ndjson_bytes(entities)
        entries, _ = await _fetch_and_parse_opensanctions_default(
            client_factory=lambda: _FakeAsyncClient([payload])
        )
        assert entries[0]["primary_name"] == "张三"
        assert entries[0]["aliases"][0]["name"] == "Zhāng Sān"

    @pytest.mark.anyio
    async def test_streaming_vs_batch_equivalence(self, tmp_path: Path) -> None:
        """Feed the same payload in 1 chunk vs 17 arbitrarily-sized chunks; both must
        yield identical entries and identical sha256 over 1000 synthetic rows."""
        from app.services.sanctions import _fetch_and_parse_opensanctions_default

        entities = [
            {
                "id": f"id-{i}",
                "caption": f"Person {i}",
                "schema": "Person",
                "properties": {"name": [f"Person {i}"], "country": ["us"]},
            }
            for i in range(1000)
        ]
        payload = _make_ndjson_bytes(entities)
        (tmp_path / "sample.ndjson").write_bytes(payload)

        # single chunk
        one, h1 = await _fetch_and_parse_opensanctions_default(
            client_factory=lambda: _FakeAsyncClient([payload])
        )
        # 17 chunks of arbitrary size
        step = max(1, len(payload) // 17)
        multi_chunks = [payload[i : i + step] for i in range(0, len(payload), step)]
        many, h2 = await _fetch_and_parse_opensanctions_default(
            client_factory=lambda: _FakeAsyncClient(multi_chunks)
        )

        assert h1 == h2 == hashlib.sha256(payload).hexdigest()
        assert len(one) == len(many) == 1000
        assert [e["ref_id"] for e in one] == [e["ref_id"] for e in many]

    @pytest.mark.anyio
    async def test_skips_malformed_lines(self) -> None:
        from app.services.sanctions import _fetch_and_parse_opensanctions_default

        good = json.dumps(
            {
                "id": "g",
                "caption": "Good",
                "schema": "Person",
                "properties": {"name": ["Good"]},
            }
        ).encode()
        payload = good + b"\n" + b"{not json\n" + good + b"\n"
        entries, _ = await _fetch_and_parse_opensanctions_default(
            client_factory=lambda: _FakeAsyncClient([payload])
        )
        # two good entries, malformed dropped
        assert len(entries) == 2


# ---------------------------------------------------------------------------
# 4.  SANCTIONS_SKIP_OPENSANCTIONS_DEFAULT env gate
# ---------------------------------------------------------------------------


class TestSkipEnvGate:
    @pytest.mark.anyio
    async def test_default_source_included_when_env_not_set(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.services import sanctions as sanc

        monkeypatch.delenv("SANCTIONS_SKIP_OPENSANCTIONS_DEFAULT", raising=False)
        monkeypatch.setenv("SANCTIONS_SKIP_PEP", "1")  # keep PEP noise out

        mock_db = AsyncMock()
        mock_snap = MagicMock()
        mock_snap.entry_count = 0
        with (
            patch.object(
                sanc, "_fetch_and_parse_un", new_callable=AsyncMock, return_value=([], "h1")
            ),
            patch.object(
                sanc, "_fetch_and_parse_uk_ofsi", new_callable=AsyncMock, return_value=([], "h2")
            ),
            patch.object(
                sanc, "_fetch_and_parse_eu", new_callable=AsyncMock, return_value=([], "h3")
            ),
            patch.object(
                sanc,
                "refresh_opensanctions_default",
                new_callable=AsyncMock,
                return_value=(mock_snap, True),
            ),
            patch.object(
                sanc, "_store_snapshot", new_callable=AsyncMock, return_value=(MagicMock(), True)
            ),
        ):
            results = await sanc.refresh_additional_lists(mock_db)

        assert "opensanctions_default" in [s for s, _ in results]

    @pytest.mark.anyio
    async def test_default_source_skipped_when_env_is_1(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.services import sanctions as sanc

        monkeypatch.setenv("SANCTIONS_SKIP_OPENSANCTIONS_DEFAULT", "1")
        monkeypatch.setenv("SANCTIONS_SKIP_PEP", "1")

        mock_db = AsyncMock()
        with (
            patch.object(
                sanc, "_fetch_and_parse_un", new_callable=AsyncMock, return_value=([], "h1")
            ),
            patch.object(
                sanc, "_fetch_and_parse_uk_ofsi", new_callable=AsyncMock, return_value=([], "h2")
            ),
            patch.object(
                sanc, "_fetch_and_parse_eu", new_callable=AsyncMock, return_value=([], "h3")
            ),
            patch.object(
                sanc,
                "refresh_opensanctions_default",
                new_callable=AsyncMock,
            ) as refresh_default,
            patch.object(
                sanc, "_store_snapshot", new_callable=AsyncMock, return_value=(MagicMock(), True)
            ),
        ):
            results = await sanc.refresh_additional_lists(mock_db)

        assert "opensanctions_default" not in [s for s, _ in results]
        refresh_default.assert_not_called()


# ---------------------------------------------------------------------------
# 5.  Fuzzy scorer upgrade
# ---------------------------------------------------------------------------


class TestComputeNameScore:
    def test_exact_case_insensitive_primary_short_circuits(self) -> None:
        """An exact (case-insensitive) match against primary_name returns
        (100, matched_name) without calling rapidfuzz."""
        from app.services import sanctions as sanc

        entry = MagicMock()
        entry.primary_name = "Carrie Lam"
        entry.aliases = []

        with patch.object(sanc.fuzz, "token_set_ratio") as scorer:
            score, name = sanc._compute_name_score("carrie lam", entry)

        assert score == 100
        assert name == "Carrie Lam"
        scorer.assert_not_called()

    def test_exact_case_insensitive_alias_short_circuits(self) -> None:
        from app.services import sanctions as sanc

        entry = MagicMock()
        entry.primary_name = "LAM, Cheng Yuet-Ngor"
        entry.aliases = [{"type": "a.k.a.", "name": "LAM, Carrie"}]

        with patch.object(sanc.fuzz, "token_set_ratio") as scorer:
            score, name = sanc._compute_name_score("lam, carrie", entry)

        assert score == 100
        assert name == "LAM, Carrie"
        scorer.assert_not_called()

    def test_carrie_lam_alias_fuzzy_match_is_confirmed(self) -> None:
        """'Carrie Lam' vs alias 'LAM, Carrie' should score ≥ confirmed
        threshold (85) with the token_set_ratio scorer."""
        from app.services.sanctions import _CONFIRMED_MATCH_THRESHOLD, _compute_name_score

        entry = MagicMock()
        entry.primary_name = "LAM, Cheng Yuet-Ngor"
        entry.aliases = [{"type": "a.k.a.", "name": "LAM, Carrie"}]

        score, matched = _compute_name_score("Carrie Lam", entry)
        assert score >= _CONFIRMED_MATCH_THRESHOLD
        assert matched == "LAM, Carrie"

    def test_jonathan_smith_is_potential_match(self) -> None:
        """'Jonathan Smith' vs 'Smith, John' should land in the potential
        band (70 ≤ score < 85)."""
        from app.services.sanctions import (
            _CONFIRMED_MATCH_THRESHOLD,
            _POTENTIAL_MATCH_THRESHOLD,
            _compute_name_score,
        )

        entry = MagicMock()
        entry.primary_name = "Smith, John"
        entry.aliases = []

        score, _ = _compute_name_score("Jonathan Smith", entry)
        assert _POTENTIAL_MATCH_THRESHOLD <= score < _CONFIRMED_MATCH_THRESHOLD

    def test_thresholds_are_70_and_85(self) -> None:
        from app.services.sanctions import (
            _CONFIRMED_MATCH_THRESHOLD,
            _POTENTIAL_MATCH_THRESHOLD,
        )

        assert _POTENTIAL_MATCH_THRESHOLD == 70
        assert _CONFIRMED_MATCH_THRESHOLD == 85


# ---------------------------------------------------------------------------
# 6.  screen_contact end-to-end (SQLite)
# ---------------------------------------------------------------------------


@pytest.fixture()
def sqlite_engine() -> sa.engine.Engine:
    """Sync SQLite engine with all ORM tables, used for setup."""
    eng = create_engine("sqlite:///:memory:", echo=False)

    @event.listens_for(eng, "connect")
    def _pragma(dbapi_conn, connection_record):  # type: ignore[no-untyped-def]
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=OFF")
        cursor.close()

    from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler

    if not hasattr(SQLiteTypeCompiler, "visit_JSONB"):
        SQLiteTypeCompiler.visit_JSONB = lambda self, type_, **kw: "TEXT"  # type: ignore[attr-defined]
    if not hasattr(SQLiteTypeCompiler, "visit_UUID"):
        SQLiteTypeCompiler.visit_UUID = lambda self, type_, **kw: "VARCHAR(36)"  # type: ignore[attr-defined]
    if not hasattr(SQLiteTypeCompiler, "visit_TIMESTAMP"):
        SQLiteTypeCompiler.visit_TIMESTAMP = lambda self, type_, **kw: "TIMESTAMP"  # type: ignore[attr-defined]
    if not hasattr(SQLiteTypeCompiler, "visit_INET"):
        SQLiteTypeCompiler.visit_INET = lambda self, type_, **kw: "TEXT"  # type: ignore[attr-defined]
    if not hasattr(SQLiteTypeCompiler, "visit_LargeBinary"):
        SQLiteTypeCompiler.visit_LargeBinary = lambda self, type_, **kw: "BLOB"  # type: ignore[attr-defined]

    from app.core.db import Base

    Base.metadata.create_all(eng)
    return eng


@pytest.fixture()
def sync_session(sqlite_engine: sa.engine.Engine) -> Generator[Session, None, None]:
    factory = sessionmaker(bind=sqlite_engine)
    s = factory()
    yield s
    s.close()


def _seed_snapshot_with_carrie_lam(session: Session) -> tuple[str, str]:
    """Insert an active snapshot + one Carrie Lam entry. Returns (snapshot_id, entry_id)."""
    from app.infra.models import SanctionsListEntry, SanctionsListSnapshot

    snap = SanctionsListSnapshot(
        id=str(uuid.uuid4()),
        source="opensanctions_default",
        fetched_at=datetime.now(tz=UTC),
        entry_count=1,
        sha256_hash="a" * 64,
        is_active=True,
        notes=None,
    )
    session.add(snap)
    session.flush()

    entry = SanctionsListEntry(
        id=str(uuid.uuid4()),
        snapshot_id=snap.id,
        ref_id="ofac-lam",
        entity_type="individual",
        primary_name="LAM, Cheng Yuet-Ngor",
        aliases=[{"type": "a.k.a.", "name": "LAM, Carrie"}],
        countries=["hk"],
        programs=["sanction"],
        remarks=None,
        source="opensanctions_default",
    )
    session.add(entry)
    session.flush()
    return snap.id, entry.id


def _seed_snapshot_with_john_smith(session: Session) -> None:
    from app.infra.models import SanctionsListEntry, SanctionsListSnapshot

    snap = SanctionsListSnapshot(
        id=str(uuid.uuid4()),
        source="ofac_consolidated",
        fetched_at=datetime.now(tz=UTC),
        entry_count=1,
        sha256_hash="b" * 64,
        is_active=True,
        notes=None,
    )
    session.add(snap)
    session.flush()
    session.add(
        SanctionsListEntry(
            id=str(uuid.uuid4()),
            snapshot_id=snap.id,
            ref_id="ofac-js",
            entity_type="individual",
            primary_name="Smith, John",
            aliases=[],
            countries=["us"],
            programs=["sanction"],
            remarks=None,
            source="ofac_consolidated",
        )
    )
    session.flush()


def _make_contact(session: Session, tenant_id: str, name: str, country: str | None = None) -> str:
    from app.infra.models import Contact

    cid = str(uuid.uuid4())
    c = Contact(
        id=cid,
        tenant_id=tenant_id,
        contact_type="customer",
        name=name,
        country=country,
        is_archived=False,
        created_at=datetime.now(tz=UTC),
        updated_at=datetime.now(tz=UTC),
    )
    session.add(c)
    session.flush()
    return cid


def _make_kyc(session: Session, tenant_id: str, contact_id: str) -> None:
    from app.infra.models import ContactKyc

    session.add(
        ContactKyc(
            id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            contact_id=contact_id,
            sanctions_status="clear",
            created_at=datetime.now(tz=UTC),
            updated_at=datetime.now(tz=UTC),
        )
    )
    session.flush()


class TestScreenContactEndToEnd:
    @pytest.mark.anyio
    async def test_carrie_lam_is_confirmed_match(self, sync_session: Session) -> None:
        """Contact 'Carrie Lam' screened against a snapshot containing
        'LAM, Cheng Yuet-Ngor' aka 'LAM, Carrie' → confirmed_match + kyc.flagged."""
        from app.services.sanctions import screen_contact

        _seed_snapshot_with_carrie_lam(sync_session)
        tenant_id = str(uuid.uuid4())
        cid = _make_contact(sync_session, tenant_id, "Carrie Lam", country="HK")
        _make_kyc(sync_session, tenant_id, cid)
        sync_session.commit()

        # Wrap the sync session's connection in an AsyncSession via the
        # same in-memory DB URL is tricky; easier: use the sync session
        # directly since the service only needs an AsyncSession interface.
        # We build an AsyncSession from a fresh async engine sharing a
        # :memory: URI via uri=true? Simpler path: use an async-compatible
        # in-memory sqlite via aiosqlite — but that requires an extra dep.
        # Instead we assert against an AsyncSession-shaped adapter.
        async with _async_session_from_sync(sync_session) as db:
            result = await screen_contact(
                db,
                contact_id=cid,
                tenant_id=tenant_id,
                contact_name="Carrie Lam",
                contact_country="HK",
            )
        assert result.match_status == "confirmed_match"
        assert result.match_score >= 85
        assert result.matched_name == "LAM, Carrie"

        # KYC side-effect
        from app.infra.models import ContactKyc

        kyc = sync_session.query(ContactKyc).filter_by(contact_id=cid).one()
        assert kyc.sanctions_status == "flagged"

    @pytest.mark.anyio
    async def test_jonathan_smith_is_potential_match(self, sync_session: Session) -> None:
        from app.services.sanctions import screen_contact

        _seed_snapshot_with_john_smith(sync_session)
        tenant_id = str(uuid.uuid4())
        cid = _make_contact(sync_session, tenant_id, "Jonathan Smith", country="US")
        _make_kyc(sync_session, tenant_id, cid)
        sync_session.commit()

        async with _async_session_from_sync(sync_session) as db:
            result = await screen_contact(
                db,
                contact_id=cid,
                tenant_id=tenant_id,
                contact_name="Jonathan Smith",
                contact_country="US",
            )
        assert result.match_status == "potential_match"
        assert 70 <= result.match_score < 85

        from app.infra.models import ContactKyc

        kyc = sync_session.query(ContactKyc).filter_by(contact_id=cid).one()
        assert kyc.sanctions_status == "under_review"


class _AsyncSessionAdapter:
    """A tiny adapter that exposes the methods used by the sanctions
    service (``execute``, ``scalar``, ``add``, ``flush``) over a
    synchronous SQLAlchemy ``Session``."""

    def __init__(self, sync: Session) -> None:
        self._sync = sync

    async def __aenter__(self) -> _AsyncSessionAdapter:
        return self

    async def __aexit__(self, *args: Any) -> None:
        return None

    async def execute(self, *a: Any, **kw: Any) -> Any:
        return self._sync.execute(*a, **kw)

    async def scalar(self, *a: Any, **kw: Any) -> Any:
        return self._sync.scalar(*a, **kw)

    def add(self, obj: Any) -> None:
        self._sync.add(obj)

    def add_all(self, objs: Any) -> None:
        self._sync.add_all(objs)

    async def flush(self) -> None:
        self._sync.flush()

    async def commit(self) -> None:
        self._sync.commit()

    async def rollback(self) -> None:
        self._sync.rollback()


def _async_session_from_sync(sync: Session) -> _AsyncSessionAdapter:
    return _AsyncSessionAdapter(sync)


# ---------------------------------------------------------------------------
# 7.  Audit event on changed snapshot
# ---------------------------------------------------------------------------


class TestAuditEventOnSnapshotStore:
    @pytest.mark.anyio
    async def test_emits_audit_event_when_snapshot_changes(self) -> None:
        """_store_snapshot should call the audit emitter when the hash
        is different from the previous snapshot (is_changed=True)."""
        from app.services import sanctions as sanc

        db = AsyncMock()
        # No previous snapshot — so this IS a change
        db.scalar = AsyncMock(return_value=None)
        # .add / .add_all are synchronous on AsyncSession — use MagicMock
        db.add = MagicMock()
        db.add_all = MagicMock()

        with patch("app.audit.emitter.emit", new_callable=AsyncMock) as mock_emit:
            snap, changed = await sanc._store_snapshot(
                db,
                source="opensanctions_default",
                entries=[
                    {
                        "ref_id": "a",
                        "entity_type": "individual",
                        "primary_name": "Alice",
                        "aliases": [],
                        "countries": [],
                        "programs": [],
                        "remarks": None,
                        "source": "opensanctions_default",
                    }
                ],
                raw_hash="deadbeef",
            )

        assert changed is True
        mock_emit.assert_awaited_once()
        call_kwargs = mock_emit.call_args.kwargs
        assert call_kwargs["action"] == "sanctions.list_refreshed"
        assert call_kwargs["entity_type"] == "sanctions_snapshot"
        assert call_kwargs["actor_type"] == "system"
        assert call_kwargs["tenant_id"] is None
        assert call_kwargs["metadata"]["source"] == "opensanctions_default"
        assert call_kwargs["metadata"]["entry_count"] == 1

    @pytest.mark.anyio
    async def test_does_not_emit_audit_event_when_unchanged(self) -> None:
        from app.services import sanctions as sanc

        prev = MagicMock()
        prev.sha256_hash = "samehash"
        prev.is_active = True

        db = AsyncMock()
        db.scalar = AsyncMock(return_value=prev)

        with patch("app.audit.emitter.emit", new_callable=AsyncMock) as mock_emit:
            _, changed = await sanc._store_snapshot(
                db,
                source="opensanctions_default",
                entries=[],
                raw_hash="samehash",
            )

        assert changed is False
        mock_emit.assert_not_called()


# ---------------------------------------------------------------------------
# 8.  refresh_additional_lists includes new source (name assertion)
# ---------------------------------------------------------------------------


class TestRefreshAdditionalListsIncludesDefault:
    @pytest.mark.anyio
    async def test_default_source_present_in_results(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.services import sanctions as sanc

        monkeypatch.delenv("SANCTIONS_SKIP_OPENSANCTIONS_DEFAULT", raising=False)
        monkeypatch.setenv("SANCTIONS_SKIP_PEP", "1")

        mock_db = AsyncMock()
        mock_snap = MagicMock()
        mock_snap.entry_count = 0
        with (
            patch.object(
                sanc, "_fetch_and_parse_un", new_callable=AsyncMock, return_value=([], "h1")
            ),
            patch.object(
                sanc, "_fetch_and_parse_uk_ofsi", new_callable=AsyncMock, return_value=([], "h2")
            ),
            patch.object(
                sanc, "_fetch_and_parse_eu", new_callable=AsyncMock, return_value=([], "h3")
            ),
            patch.object(
                sanc,
                "refresh_opensanctions_default",
                new_callable=AsyncMock,
                return_value=(mock_snap, True),
            ),
            patch.object(
                sanc, "_store_snapshot", new_callable=AsyncMock, return_value=(MagicMock(), True)
            ),
        ):
            results = await sanc.refresh_additional_lists(mock_db)

        sources = [s for s, _ in results]
        assert "opensanctions_default" in sources


# ---------------------------------------------------------------------------
# 9.  NDJSON fixture file parses cleanly
# ---------------------------------------------------------------------------


class TestFixtureFile:
    def test_bundled_fixture_parses(self) -> None:
        from app.services.sanctions import _parse_opensanctions_default_line

        raw = (FIXTURES / "opensanctions_default_sample.ndjson").read_bytes()
        lines = raw.split(b"\n")
        parsed = [e for e in (_parse_opensanctions_default_line(ln) for ln in lines) if e]
        # 4 valid (Carrie Lam, Jane Doe, Acme Corp, MV Ghost) + 1 malformed dropped
        assert len(parsed) == 4
        names = [p["primary_name"] for p in parsed]
        assert "LAM, Cheng Yuet-Ngor" in names
        assert "Acme Corporation" in names
        assert "MV Ghost Ship" in names
