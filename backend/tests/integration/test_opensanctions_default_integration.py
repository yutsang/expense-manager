"""End-to-end integration test for the OpenSanctions Default feed (SQLite).

Verifies that a full refresh → screen_contact round-trip works against the
real ORM schema with an on-disk NDJSON fixture substituted for the live feed.
The critical assertion is the Carrie Lam alias case (issue #77).
"""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import AsyncIterator, Generator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

FIXTURES = Path(__file__).parents[1] / "unit" / "fixtures"


@pytest.fixture()
def sqlite_engine() -> sa.engine.Engine:
    eng = create_engine("sqlite:///:memory:", echo=False)

    @event.listens_for(eng, "connect")
    def _pragma(dbapi_conn, connection_record):  # type: ignore[no-untyped-def]
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=OFF")
        cursor.close()

    from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler

    _orig_jsonb = getattr(SQLiteTypeCompiler, "visit_JSONB", None)
    if _orig_jsonb is None:
        SQLiteTypeCompiler.visit_JSONB = lambda self, type_, **kw: "TEXT"  # type: ignore[attr-defined]
    _orig_uuid = getattr(SQLiteTypeCompiler, "visit_UUID", None)
    if _orig_uuid is None:
        SQLiteTypeCompiler.visit_UUID = lambda self, type_, **kw: "VARCHAR(36)"  # type: ignore[method-assign]
    _orig_ts = getattr(SQLiteTypeCompiler, "visit_TIMESTAMP", None)
    if _orig_ts is None:
        SQLiteTypeCompiler.visit_TIMESTAMP = lambda self, type_, **kw: "TIMESTAMP"  # type: ignore[method-assign]
    _orig_inet = getattr(SQLiteTypeCompiler, "visit_INET", None)
    if _orig_inet is None:
        SQLiteTypeCompiler.visit_INET = lambda self, type_, **kw: "TEXT"  # type: ignore[attr-defined]
    _orig_lb = getattr(SQLiteTypeCompiler, "visit_LargeBinary", None)
    if _orig_lb is None:
        SQLiteTypeCompiler.visit_LargeBinary = lambda self, type_, **kw: "BLOB"  # type: ignore[attr-defined]

    # Import models so their tables are registered on Base.metadata
    import app.infra.models  # noqa: F401
    from app.core.db import Base

    Base.metadata.create_all(eng)
    return eng


@pytest.fixture()
def session(sqlite_engine: sa.engine.Engine) -> Generator[Session, None, None]:
    factory = sessionmaker(bind=sqlite_engine)
    s = factory()
    yield s
    s.close()


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
    def __init__(self, chunks: list[bytes]) -> None:
        self._chunks = chunks

    async def __aenter__(self) -> _FakeAsyncClient:
        return self

    async def __aexit__(self, *args: Any) -> None:
        return None

    def stream(self, method: str, url: str) -> _FakeStreamResponse:
        return _FakeStreamResponse(self._chunks)


class _AsyncSessionAdapter:
    """Minimal AsyncSession-shaped wrapper over a sync Session."""

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

    async def delete(self, obj: Any) -> None:
        self._sync.delete(obj)

    def expunge(self, obj: Any) -> None:
        self._sync.expunge(obj)


class TestOpenSanctionsDefaultIntegration:
    @pytest.mark.anyio
    async def test_refresh_then_screen_carrie_lam(self, session: Session) -> None:
        """Run the default refresh pipeline against the bundled NDJSON fixture,
        then screen a contact named 'Carrie Lam' — must be confirmed_match."""
        from app.infra.models import (
            Contact,
            ContactKyc,
            SanctionsListEntry,
            SanctionsListSnapshot,
        )
        from app.services.sanctions import (
            _OPENSANCTIONS_PARSER_VERSION,
            refresh_opensanctions_default,
            screen_contact,
        )

        payload = (FIXTURES / "opensanctions_default_sample.ndjson").read_bytes()
        # Hash is bytes-hash folded with the parser version.
        _h = hashlib.sha256()
        _h.update(hashlib.sha256(payload).digest())
        _h.update(_OPENSANCTIONS_PARSER_VERSION.encode())
        expected_hash = _h.hexdigest()

        db = _AsyncSessionAdapter(session)

        # Feed our fixture bytes through the real streaming implementation
        # via the client_factory hook that both the buffered and streaming
        # paths expose. No monkey-patching needed.
        def fake_client_factory() -> _FakeAsyncClient:
            return _FakeAsyncClient([payload])

        snapshot, changed = await refresh_opensanctions_default(
            db,  # type: ignore[arg-type]
            client_factory=fake_client_factory,  # type: ignore[arg-type]
        )
        assert changed is True
        assert snapshot.sha256_hash == expected_hash

        # Sanity: snapshot & entries landed in SQLite
        rows = session.query(SanctionsListEntry).filter_by(snapshot_id=snapshot.id).all()
        assert len(rows) == 4  # 5 lines but one malformed → 4 valid
        names = [r.primary_name for r in rows]
        assert "LAM, Cheng Yuet-Ngor" in names

        # Seed a contact + kyc record and screen
        tenant_id = str(uuid.uuid4())
        contact_id = str(uuid.uuid4())
        session.add(
            Contact(
                id=contact_id,
                tenant_id=tenant_id,
                contact_type="customer",
                name="Carrie Lam",
                country="HK",
                is_archived=False,
                created_at=datetime.now(tz=UTC),
                updated_at=datetime.now(tz=UTC),
            )
        )
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

        result = await screen_contact(
            db,  # type: ignore[arg-type]
            contact_id=contact_id,
            tenant_id=tenant_id,
            contact_name="Carrie Lam",
            contact_country="HK",
        )
        assert result.match_status == "confirmed_match"
        assert result.match_score >= 85
        # Either the exact-match alias ("Carrie Lam") or the token-swapped
        # variant ("LAM, Carrie") is an acceptable matched_name — both
        # resolve to the same SanctionsListEntry.
        assert result.matched_name in {"Carrie Lam", "LAM, Carrie"}

        kyc = session.query(ContactKyc).filter_by(contact_id=contact_id).one()
        assert kyc.sanctions_status == "flagged"

        # And: an audit event was written for the changed snapshot
        from app.infra.models import AuditEvent

        events = (
            session.query(AuditEvent)
            .filter_by(action="sanctions.list_refreshed", entity_type="sanctions_snapshot")
            .all()
        )
        assert len(events) == 1
        assert events[0].metadata_["source"] == "opensanctions_default"
        assert events[0].metadata_["entry_count"] == 4
        assert events[0].tenant_id is None

        # Assert snapshot unchanged on second call → no new audit event
        _, changed2 = await refresh_opensanctions_default(
            db,  # type: ignore[arg-type]
            client_factory=fake_client_factory,  # type: ignore[arg-type]
        )
        # Second refresh: same hash → changed should be False, no new audit event
        assert changed2 is False
        events2 = (
            session.query(AuditEvent)
            .filter_by(action="sanctions.list_refreshed", entity_type="sanctions_snapshot")
            .all()
        )
        assert len(events2) == 1

        # Silence unused imports
        _ = SanctionsListSnapshot

    @pytest.mark.anyio
    async def test_streaming_batches_bound_memory(self, session: Session) -> None:
        """Streaming insert must flush to DB every ``batch_size`` entries and
        expunge them from the session so peak Python memory stays bounded.
        Regression guard for the 2026-04-24 prod OOM where the old buffered
        implementation held all ~1.5M parsed dicts in one list.
        """
        from app.infra.models import SanctionsListEntry, SanctionsListSnapshot
        from app.services.sanctions import refresh_opensanctions_default

        # Build 1200 synthetic FtM entities → 3 batches at batch_size=500.
        def _make_line(i: int) -> bytes:
            return (
                b'{"id":"ent-'
                + str(i).encode()
                + b'","schema":"Person","caption":"Test Person '
                + str(i).encode()
                + b'","properties":{"name":["Test Person '
                + str(i).encode()
                + b'"]}}\n'
            )

        payload = b"".join(_make_line(i) for i in range(1200))

        def client_factory_mem() -> _FakeAsyncClient:
            return _FakeAsyncClient([payload])

        # Instrument flush() to count flushes and record session size at each.
        adapter = _AsyncSessionAdapter(session)
        flush_count = 0
        session_sizes_at_flush: list[int] = []
        orig_flush = adapter.flush

        async def counting_flush() -> None:
            nonlocal flush_count
            flush_count += 1
            session_sizes_at_flush.append(len(session.new))
            await orig_flush()

        adapter.flush = counting_flush  # type: ignore[method-assign]

        snapshot, changed = await refresh_opensanctions_default(
            adapter,  # type: ignore[arg-type]
            client_factory=client_factory_mem,  # type: ignore[arg-type]
            batch_size=500,
        )
        assert changed is True
        assert snapshot.entry_count == 1200

        # Persisted all 1200 rows
        rows = session.query(SanctionsListEntry).filter_by(snapshot_id=snapshot.id).count()
        assert rows == 1200

        # Expect: 1 flush for staging create + 3 batch flushes (500+500+200)
        #   + 1 flush for activation = 5. Allow >= 4 batch flushes to tolerate
        # minor internals changes.
        assert flush_count >= 4

        # At no batch flush should the pending-new set have exceeded batch_size
        # + a small epsilon for the snapshot/audit objects.
        assert max(session_sizes_at_flush) <= 510, (
            f"Pending-new set grew to {max(session_sizes_at_flush)} — streaming "
            "is not actually batching"
        )

        # silence unused
        _ = SanctionsListSnapshot
