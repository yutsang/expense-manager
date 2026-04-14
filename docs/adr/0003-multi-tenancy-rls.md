# ADR 0003 — Multi-Tenancy via Postgres Row-Level Security

**Date:** 2026-04-14
**Status:** Accepted

---

## Context

Aegis ERP is multi-tenant SaaS. Every business record belongs to exactly one tenant. Cross-tenant data leakage is a P0 security incident with legal liability. We need defense in depth.

## Decision

**Three enforcement layers, all required:**

1. **JWT-derived context var** — middleware extracts `tenant_id` from the validated JWT and stores it in an async `ContextVar`. Never accepted from request body/query params.

2. **Postgres Row-Level Security (RLS)** — every tenant-scoped table has:
   ```sql
   ALTER TABLE <table> ENABLE ROW LEVEL SECURITY;
   CREATE POLICY tenant_isolation ON <table>
     USING (tenant_id = current_setting('app.tenant_id')::uuid);
   ```
   The SQLAlchemy session sets `SET LOCAL app.tenant_id = '...'` at the start of every request.

3. **SQLAlchemy event listener** — `before_execute` event validates that every SELECT/INSERT/UPDATE/DELETE on a tenant-scoped model includes a `tenant_id` filter. This catches mistakes that RLS alone would silently hide.

**Tenant isolation integration test** (`tests/integration/test_tenant_isolation.py`) creates two tenants, writes data for each, and asserts zero leakage across all CRUD paths. This test runs in CI on every PR.

## Consequences

- ORM models must include `tenant_id` on every tenant-scoped table.
- RLS policies must be added in the same migration as the table creation.
- Code that intentionally accesses cross-tenant data (admin tooling, aggregates) must use a privileged DB role that bypasses RLS — and must be audited.
- The integration test is a **blocking** CI gate; it cannot be skipped.
