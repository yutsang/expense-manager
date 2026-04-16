"""Evidence package builder — produces an in-memory ZIP for auditor download."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import zipfile
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infra.models import AuditEvent, JournalEntry, JournalLine
from app.services.audit import verify_chain


def _isodate(d: Any) -> str:
    if isinstance(d, datetime):
        return d.isoformat()
    return str(d)


async def build_evidence_package(
    db: AsyncSession,
    tenant_id: str,
    *,
    from_date: date,
    to_date: date,
    created_by: str,
) -> bytes:
    """Build a ZIP in memory containing audit evidence for the given date range.

    Contents:
    - journals.csv
    - journal_lines.csv
    - audit_events.csv
    - chain_verification.json
    - manifest.json
    - README.txt
    """
    from_dt = datetime(from_date.year, from_date.month, from_date.day, tzinfo=UTC)
    to_dt = datetime(to_date.year, to_date.month, to_date.day, 23, 59, 59, tzinfo=UTC)

    # ── Fetch journal entries in range ──────────────────────────────────────
    je_result = await db.execute(
        select(JournalEntry)
        .where(
            JournalEntry.tenant_id == tenant_id,
            JournalEntry.status == "posted",
            JournalEntry.date >= from_dt,
            JournalEntry.date <= to_dt,
        )
        .order_by(JournalEntry.date.asc(), JournalEntry.number.asc())
    )
    journals = list(je_result.scalars().all())
    journal_ids = [je.id for je in journals]

    # ── Fetch journal lines for those entries ───────────────────────────────
    lines: list[JournalLine] = []
    if journal_ids:
        lines_result = await db.execute(
            select(JournalLine)
            .where(JournalLine.journal_entry_id.in_(journal_ids))
            .order_by(JournalLine.journal_entry_id.asc(), JournalLine.line_no.asc())
        )
        lines = list(lines_result.scalars().all())

    # ── Fetch audit events in range ─────────────────────────────────────────
    ae_result = await db.execute(
        select(AuditEvent)
        .where(
            AuditEvent.tenant_id == tenant_id,
            AuditEvent.occurred_at >= from_dt,
            AuditEvent.occurred_at <= to_dt,
        )
        .order_by(AuditEvent.occurred_at.asc(), AuditEvent.id.asc())
    )
    audit_events = list(ae_result.scalars().all())

    # ── Run chain verification ──────────────────────────────────────────────
    chain_result = await verify_chain(db, tenant_id)

    # ── Build CSV files ─────────────────────────────────────────────────────

    def _csv_bytes(headers: list[str], rows: list[list[Any]]) -> bytes:
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(headers)
        writer.writerows(rows)
        return buf.getvalue().encode("utf-8")

    journals_csv = _csv_bytes(
        ["id", "number", "date", "description", "total_debit", "total_credit", "currency", "status", "posted_at", "posted_by"],
        [
            [
                je.id, je.number, _isodate(je.date), je.description,
                str(je.total_debit), str(je.total_credit), je.currency,
                je.status, _isodate(je.posted_at) if je.posted_at else "",
                je.posted_by or "",
            ]
            for je in journals
        ],
    )

    journal_lines_csv = _csv_bytes(
        ["id", "journal_entry_id", "line_no", "account_id", "description", "debit", "credit", "currency"],
        [
            [
                ln.id, ln.journal_entry_id, ln.line_no, ln.account_id,
                ln.description or "", str(ln.debit), str(ln.credit), ln.currency,
            ]
            for ln in lines
        ],
    )

    audit_events_csv = _csv_bytes(
        ["id", "occurred_at", "actor_type", "actor_id", "action", "entity_type", "entity_id"],
        [
            [
                ae.id, _isodate(ae.occurred_at), ae.actor_type,
                ae.actor_id or "", ae.action, ae.entity_type, ae.entity_id or "",
            ]
            for ae in audit_events
        ],
    )

    chain_json = json.dumps(
        {
            "id": chain_result.get("id"),
            "is_valid": chain_result["is_valid"],
            "chain_length": chain_result["chain_length"],
            "last_event_id": chain_result.get("last_event_id"),
            "break_at_event_id": chain_result.get("break_at_event_id"),
            "error_message": chain_result.get("error_message"),
            "verified_at": _isodate(chain_result["verified_at"]),
        },
        indent=2,
    ).encode("utf-8")

    readme_txt = (
        "Aegis ERP — Audit Evidence Package\n"
        "====================================\n\n"
        "Files:\n"
        "  journals.csv          — All posted journal entries in the date range\n"
        "  journal_lines.csv     — Debit/credit lines for each journal entry\n"
        "  audit_events.csv      — Audit trail events in the date range\n"
        "  chain_verification.json — Hash-chain integrity verification result\n"
        "  manifest.json         — Package metadata and per-file SHA-256 hashes\n\n"
        "Verification:\n"
        "  1. Check chain_verification.json: is_valid must be true.\n"
        "  2. Recompute sha256 of each file and compare against manifest.json file_hashes.\n"
        "  3. Cross-reference journal entry IDs in journals.csv with your GL system.\n"
    ).encode()

    # ── Compute file hashes ─────────────────────────────────────────────────
    file_hashes = {
        "journals.csv": hashlib.sha256(journals_csv).hexdigest(),
        "journal_lines.csv": hashlib.sha256(journal_lines_csv).hexdigest(),
        "audit_events.csv": hashlib.sha256(audit_events_csv).hexdigest(),
        "chain_verification.json": hashlib.sha256(chain_json).hexdigest(),
        "README.txt": hashlib.sha256(readme_txt).hexdigest(),
    }

    manifest = json.dumps(
        {
            "created_at": datetime.now(tz=UTC).isoformat(),
            "from_date": from_date.isoformat(),
            "to_date": to_date.isoformat(),
            "tenant_id": tenant_id,
            "created_by": created_by,
            "journal_count": len(journals),
            "journal_line_count": len(lines),
            "audit_event_count": len(audit_events),
            "file_hashes": file_hashes,
        },
        indent=2,
    ).encode("utf-8")

    # ── Assemble ZIP ────────────────────────────────────────────────────────
    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("journals.csv", journals_csv)
        zf.writestr("journal_lines.csv", journal_lines_csv)
        zf.writestr("audit_events.csv", audit_events_csv)
        zf.writestr("chain_verification.json", chain_json)
        zf.writestr("README.txt", readme_txt)
        zf.writestr("manifest.json", manifest)

    return zip_buf.getvalue()
