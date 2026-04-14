# ADR 0002 — Append-Only Hash-Chained Audit Trail

**Date:** 2026-04-14
**Status:** Accepted

---

## Context

Accounting software requires tamper-evident logs for regulatory compliance (SOX, ISO 27001) and customer trust. We need an audit trail that:

1. Cannot be silently edited or deleted.
2. Allows detection of any gap or tampering.
3. Is queryable for auditor workspaces and evidence packages.

## Decision

**`audit_events` is append-only with a SHA-256 hash chain per tenant.**

- A Postgres trigger blocks all `UPDATE` and `DELETE` on the table at the DB layer.
- Each event stores `prev_hash` (the hash of the tenant's most recent event) and `hash = sha256(prev_hash || canonical_json(event))`.
- The first event per tenant uses a sentinel `prev_hash = 0x00...00`.
- A background worker (Phase 4) walks the chain daily and alerts on any break.

## Alternatives considered

1. **Write-ahead log (WAL) archiving only** — hard to query; relies on DBA tooling.
2. **Blockchain ledger** — overkill, operational overhead, no meaningful benefit here.
3. **External audit log service** — latency, vendor dependency, still needs the same design internally.

## Consequences

- Audit events **must** be written in the same transaction as the business change.
- All application mutations go through service layer methods; direct ORM writes bypassing the service will miss audit events.
- `before_state` / `after_state` fields auto-redact columns tagged `@pii` in Phase 1+.
- Evidence packages in Phase 4 include the chain for the exported range so recipients can verify offline.
