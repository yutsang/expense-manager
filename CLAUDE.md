# CLAUDE.md — Aegis ERP Developer Guide

> **Project codename:** Aegis ERP (working title — rename freely in `pyproject.toml`, `package.json`, and copy).
> **One-liner:** An AI-assisted, audit-first ERP & accounting platform (Xero-class) with a mobile companion and an embedded Claude assistant that reasons over the general ledger, answers auditor requests, and drafts journal entries with citations.

This file is loaded into every Claude conversation in this repo. Keep it **accurate, current, and terse**. If a rule is obsolete, delete it — don't leave a "// deprecated" comment.

---

## 0. How to use this guide

- **Read in order** when you first open the repo. Sections 1–4 are orientation; 5–17 are enforceable rules.
- **Rules marked `MUST` or `NEVER` are non-negotiable** — violating them creates financial or compliance risk.
- **When a rule conflicts with a user request**, surface the conflict before acting. Don't silently break invariants (audit log, double-entry, tenant isolation, money precision).
- **Source of truth for product scope:** `docs/PRP.md`. This file is the *how*; the PRP is the *what*.

---

## 1. Project overview

Aegis ERP is a multi-tenant SaaS platform with three surfaces:

| Surface     | Audience                           | Primary job |
|-------------|------------------------------------|-------------|
| Web app     | Accountants, bookkeepers, admins   | Full ERP + accounting workflows |
| Mobile app  | Owners, field staff, approvers     | Capture, approve, review on the go |
| API         | Third-party integrations, auditors | Programmatic access + audit export |

Four product pillars:

1. **Core ledger** — double-entry general ledger with strict period controls.
2. **AI assistant** — Claude-powered chat that can *query* and *propose* changes with citations; mutations require explicit human confirmation.
3. **Audit module** — tamper-evident audit trail, auditor workspaces, one-click evidence packages.
4. **Mobile sync** — offline-first mobile with deterministic conflict resolution.

---

## 2. Accounting domain primer (read before touching ledger code)

You are expected to understand these concepts. If you're unsure, **do not guess** — ask the user or read `docs/domain/accounting.md` (once created).

### 2.1 Double-entry bookkeeping

Every transaction is recorded as **a journal entry containing ≥ 2 lines**. Each line has either a **debit** or a **credit** amount. **Total debits MUST equal total credits** in every journal entry (the "balanced" invariant). This is enforced at three layers:

- Pydantic validator on `JournalEntryCreate`
- SQLAlchemy `@validates` on `JournalEntry`
- Postgres `CHECK` constraint via migration

If any layer is missing, the migration is incomplete. Fail the PR.

### 2.2 Account types and normal balances

| Type       | Normal balance | Increased by | Examples |
|------------|----------------|--------------|----------|
| Asset      | Debit          | Debit        | Cash, AR, Inventory |
| Liability  | Credit         | Credit       | AP, Loans, Tax payable |
| Equity     | Credit         | Credit       | Capital, Retained earnings |
| Revenue    | Credit         | Credit       | Sales, Service income |
| Expense    | Debit          | Debit        | COGS, Salaries, Rent |

Contra accounts (e.g., Accumulated Depreciation) flip the normal balance of their parent. The `chart_of_accounts` table stores `normal_balance` explicitly — **never infer it from the name**.

### 2.3 Period and closing

- Periods are typically monthly, with a fiscal-year boundary.
- Periods have status: `open`, `soft_closed`, `hard_closed`, `audited`.
- **`hard_closed` periods cannot receive new entries** — even by admins. Reopening requires an `Auditor` role action and generates an audit entry.
- Year-end close runs `close_period()` which posts closing journals (revenue/expense → retained earnings). This is idempotent and reversible only from `soft_closed`.

### 2.4 Multi-currency

- Every monetary amount has a currency (ISO 4217).
- The ledger has a **functional currency** per tenant (settable once, change requires full revaluation job).
- Foreign-currency transactions store: `original_amount`, `original_currency`, `functional_amount`, `fx_rate`, `fx_rate_source`, `fx_rate_date`.
- FX gain/loss is posted automatically on settlement and period-end revaluation.

### 2.5 Source documents

Every journal entry has ≥ 1 **source document** (invoice, bill, bank statement line, manual memo). Source docs are immutable once a journal references them; to "edit," you void + reissue. This preserves audit defensibility.

---

## 3. Architecture

```
                      ┌──────────────┐   ┌──────────────┐
                      │   Web (Next) │   │ Mobile (Expo)│
                      └──────┬───────┘   └──────┬───────┘
                             │ HTTPS/WSS        │ HTTPS/WSS
                             ▼                  ▼
                      ┌──────────────────────────────────┐
                      │   API Gateway (FastAPI, /v1)     │
                      │   - AuthN (JWT + refresh)        │
                      │   - AuthZ (RBAC + row tenant)    │
                      │   - Rate limit (per tenant+user) │
                      └──────┬──────────┬────────────────┘
                             │          │
          ┌──────────────────┤          ├─────────────────────┐
          ▼                  ▼          ▼                     ▼
   ┌────────────┐   ┌────────────────┐ ┌───────────┐   ┌──────────────┐
   │ Ledger svc │   │ AI Orchestrator│ │ Audit svc │   │ Sync service │
   │ (domain)   │   │ (Claude tools) │ │ (append)  │   │ (deltas,CRDT)│
   └─────┬──────┘   └────────┬───────┘ └─────┬─────┘   └──────┬───────┘
         │                   │               │                │
         └──────┬────────────┴───────────────┴────────────────┘
                ▼
       ┌──────────────────┐        ┌──────────────┐      ┌────────────┐
       │  PostgreSQL 16   │        │   Redis 7    │      │ S3/R2      │
       │  (RLS, NUMERIC)  │        │ cache+queue  │      │ receipts   │
       └──────────────────┘        └──────────────┘      └────────────┘
                                          ▲
                                          │
                                    ┌─────┴──────┐
                                    │  Workers   │
                                    │  (ARQ)     │
                                    └────────────┘
```

- **Monolith-first**: all services run in one FastAPI process in early phases. Module boundaries are enforced in code so they can be split later.
- **Module boundary rule**: a module may import from its own package, `app.core`, and `app.domain`. **It MUST NOT import from a sibling module's `services/` or `api/`**. Cross-module calls go through an event bus or explicit port interfaces in `app.domain.ports`.

---

## 4. Tech stack (locked decisions)

These are the defaults. Changing any requires an ADR in `docs/adr/` and explicit user approval.

### Backend

| Concern          | Choice                                  | Rationale |
|------------------|-----------------------------------------|-----------|
| Language         | Python 3.12                             | Type system + AI ecosystem |
| Web framework    | FastAPI 0.115+                          | Async, OpenAPI native, Pydantic v2 |
| ORM              | SQLAlchemy 2.0 (async)                  | Mature, supports RLS |
| Migrations       | Alembic                                 | Standard with SQLAlchemy |
| Database         | PostgreSQL 16                           | ACID, RLS, NUMERIC, JSONB |
| Cache / broker   | Redis 7                                 | Queues + rate limits + caches |
| Background jobs  | ARQ (async Redis queue)                 | Simpler than Celery, async-native |
| Object storage   | S3-compatible (MinIO dev, R2/S3 prod)   | Receipts, exports |
| AI SDK           | `anthropic` (official Python SDK)       | Claude Sonnet 4.6 default, Opus 4.6 for deep analysis, Haiku 4.5 for classifiers |
| Auth             | Custom JWT (access 15m) + refresh (30d) | Rotation on use |
| Password hashing | Argon2id (`argon2-cffi`)                | OWASP recommended |
| Validation       | Pydantic v2                             | Runtime + type |
| Observability    | OpenTelemetry + Sentry + `structlog`    | Traces, errors, logs |
| Testing          | `pytest`, `pytest-asyncio`, Hypothesis  | Unit + property-based |

### Frontend — Web

| Concern       | Choice                          |
|---------------|---------------------------------|
| Framework     | Next.js 14 (App Router)         |
| Language      | TypeScript 5 (strict)           |
| Styling       | Tailwind CSS + shadcn/ui        |
| State (server)| TanStack Query v5               |
| State (client)| Zustand                         |
| Forms         | React Hook Form + Zod           |
| Tables        | TanStack Table                  |
| Charts        | Recharts                        |
| Money         | `dinero.js` v2                  |
| API client    | OpenAPI-generated (`openapi-ts`)|
| Testing       | Vitest + Playwright             |

### Frontend — Mobile

| Concern        | Choice                         |
|----------------|--------------------------------|
| Framework      | Expo SDK 51 (React Native)     |
| Navigation     | Expo Router v3                 |
| State (server) | TanStack Query v5              |
| Local DB       | `op-sqlite`                    |
| Secure storage | `expo-secure-store`            |
| Push           | `expo-notifications`           |
| Biometric      | `expo-local-authentication`    |
| Camera/OCR     | `expo-camera` + Claude Vision  |
| Testing        | Jest + Detox                   |

### Infra

- Docker Compose for local dev.
- Terraform modules for prod (AWS: RDS, ElastiCache, S3, ALB, ECS/Fargate).
- GitHub Actions for CI (lint, typecheck, test, build, migration-safety check).

---

## 5. Repository structure

```
aegis-erp/
├── backend/
│   ├── app/
│   │   ├── core/              # config, db session, security, telemetry
│   │   ├── domain/            # pure domain models & rules (no I/O)
│   │   │   ├── ledger/        # account, journal, period
│   │   │   ├── money/         # Money, Currency, FX
│   │   │   ├── tenant/        # org, user, role
│   │   │   └── ports/         # interfaces sibling modules implement
│   │   ├── infra/             # adapters: db repos, s3, email, claude
│   │   ├── api/               # FastAPI routers, versioned /v1
│   │   │   └── v1/
│   │   ├── services/          # orchestration (use cases)
│   │   ├── workers/           # ARQ tasks
│   │   ├── ai/                # Claude integration (see §11)
│   │   │   ├── prompts/       # versioned system prompts
│   │   │   ├── tools/         # tool definitions + handlers
│   │   │   └── orchestrator.py
│   │   └── audit/             # append-only log, hash chain, exporters
│   ├── migrations/            # Alembic
│   ├── tests/
│   │   ├── unit/
│   │   ├── integration/       # hits real Postgres (see §14)
│   │   └── property/          # Hypothesis tests for money math
│   ├── pyproject.toml
│   └── Dockerfile
├── frontend/
│   ├── apps/
│   │   ├── web/               # Next.js
│   │   └── mobile/            # Expo
│   └── packages/
│       ├── ui/                # shared design-system components
│       ├── api-client/        # generated from OpenAPI
│       ├── money/             # shared Dinero wrappers
│       └── types/             # shared TS types
├── docs/
│   ├── PRP.md                 # product requirements plan
│   ├── adr/                   # architecture decision records
│   ├── domain/                # accounting/audit primers
│   └── runbooks/              # oncall / incident docs
├── infra/
│   ├── docker/                # compose files, dev services
│   └── terraform/             # prod infra
├── scripts/                   # dev scripts (seed, reset, export)
├── .github/workflows/
├── CLAUDE.md                  # this file
├── LICENSE
└── README.md
```

**Naming rules:**

- Python: `snake_case.py`, classes `PascalCase`, constants `SCREAMING_SNAKE`.
- TS/TSX: files `kebab-case.ts(x)`, React components `PascalCase` in PascalCase files *or* kebab files — be consistent per app.
- DB tables: plural, `snake_case` (`journal_entries`, not `JournalEntry`).
- Migrations: Alembic auto-names, prefix message with scope: `"ledger: add period status"`.

---

## 6. Development workflow

### First-time setup

```bash
# Clone, then
make bootstrap              # installs backend deps, frontend deps, pre-commit hooks
make up                     # docker-compose: postgres, redis, minio, mailhog
make migrate                # alembic upgrade head
make seed                   # demo tenant + chart of accounts
make dev                    # runs api, web, mobile metro in parallel (tmux/overmind)
```

If `make` targets don't exist yet, they belong in the foundation phase — create them, don't work around them.

### Daily loop

```bash
make test                   # runs fast tests only (<30s)
make test-slow              # integration + e2e
make lint                   # ruff + mypy + biome + tsc --noEmit
make fix                    # auto-fix lint issues
make migration m="ledger: add fx rate source"   # new alembic revision
```

### Git workflow

- Default branch: `main`. Protected.
- Branch naming: `feat/…`, `fix/…`, `chore/…`, `docs/…`. Include issue ID if applicable.
- Commits: Conventional Commits (`feat(ledger): …`, `fix(audit): …`).
- PRs: small, focused, one logical change. CI must be green.
- **Never force-push to `main`. Never skip hooks (`--no-verify`).** If a hook fails, fix the root cause.

---

## 7. Coding standards

### 7.1 Python

- **Black** (line length 100) + **Ruff** (lint + import sort) + **Mypy strict**.
- Type hints on **every** function signature, including tests. No `Any` without `# type: ignore[<code>]` + comment.
- Prefer `dataclass(slots=True, frozen=True)` for domain values; Pydantic for I/O boundaries.
- `from __future__ import annotations` in every new module.
- No bare `except:`. Catch narrowly. Re-raise with `raise ... from exc`.
- Repository pattern: data access is in `app/infra/repos/`. Services call repos via the `ports.*` protocols.
- **No ORM models in the API layer.** Convert to/from Pydantic schemas at the service boundary.

### 7.2 TypeScript

- `strict: true`, `noUncheckedIndexedAccess: true`, `exactOptionalPropertyTypes: true`.
- Prefer `type` over `interface` for data; `interface` only for extensible contracts.
- Zod schemas for all external data (API responses, form inputs). Infer types with `z.infer`.
- No `any` without an ESLint-disable comment explaining why. Prefer `unknown` + narrow.
- React: function components only. No class components. Hooks follow exhaustive-deps.

### 7.3 SQL / migrations

- Every migration has an `upgrade()` **and** a working `downgrade()`. No exceptions.
- Adding a `NOT NULL` column: three-step (add nullable → backfill → set NOT NULL) on tables > 10k rows.
- Indexes: add `CONCURRENTLY` in prod migrations; plain in dev seeds.
- Foreign keys: always with `ON DELETE` clause explicit (`RESTRICT` by default; `CASCADE` only for owned child rows).
- Every table has: `id (UUID v7)`, `tenant_id (UUID)`, `created_at`, `updated_at`, `created_by`, `updated_by`, `version (int, optimistic lock)`.
- Ledger tables additionally have: `locked` (bool, set when period closes).

---

## 8. Financial precision rules — **CRITICAL**

Money bugs are silent and devastating. The following are **non-negotiable**:

1. **NEVER use `float` or `Number` for money**. Ever. Not for totals, not for tax, not for display.
2. **Backend**: `decimal.Decimal` with explicit context `Decimal("1.2345")`. Never `Decimal(1.23)` (that converts from float).
3. **Database**: `NUMERIC(19, 4)` for all money columns. Store 4 decimal places; round for display.
4. **Frontend**: `dinero.js` v2 with `bigint` amounts in minor units (e.g., cents). Convert to display only via `toFormat()`.
5. **Rounding**: `ROUND_HALF_EVEN` (banker's rounding). Round only at presentation or at defined settlement points — never mid-calculation.
6. **Equality**: two `Money` values are equal iff same currency and exact amount. **Never compare across currencies**; raise `CurrencyMismatchError`.
7. **Arithmetic**: addition/subtraction require same currency. Multiplication by `Decimal` (for tax, FX) is allowed; multiplication by another `Money` is not.
8. **Serialization**: money is `{ "amount": "1234.5600", "currency": "USD" }` as a string-quoted decimal in JSON. **Never a float in JSON.** Fail loudly if encountered on input.

The `app.domain.money` package wraps all of this. **Use it. Do not import `Decimal` directly in non-money modules.**

---

## 9. Multi-tenancy model

Every business record belongs to exactly one `tenant_id` (= one organization). Cross-tenant access is a P0 security incident.

### Enforcement layers (defense in depth)

1. **JWT carries `tenant_id`**. Middleware extracts and injects into a `ContextVar`.
2. **Postgres Row-Level Security (RLS)** is enabled on every tenant-scoped table:
   ```sql
   ALTER TABLE journal_entries ENABLE ROW LEVEL SECURITY;
   CREATE POLICY tenant_isolation ON journal_entries
     USING (tenant_id = current_setting('app.tenant_id')::uuid);
   ```
   The SQLAlchemy session sets `app.tenant_id` per request.
3. **SQLAlchemy event listener** auto-filters queries by `tenant_id` and blocks inserts without it.
4. **Tests**: every integration test runs once per tenant and asserts zero leakage (see `tests/integration/test_tenant_isolation.py`).

**NEVER** accept `tenant_id` from the request body or query string. It comes from the JWT, period. If you see code doing `body.tenant_id`, delete it.

### Roles

| Role        | Capabilities |
|-------------|--------------|
| `owner`     | Everything + billing + delete tenant |
| `admin`     | Everything except billing/delete |
| `accountant`| Post journals, reconcile, run reports, close periods |
| `bookkeeper`| Enter invoices/bills, upload receipts, draft journals |
| `approver`  | Approve/reject items in approval queues |
| `viewer`    | Read-only |
| `auditor`   | Read-only + access audit module + export evidence packages |
| `api_client`| Scoped by OAuth scopes (for integrations) |

Permissions are enforced via FastAPI dependencies: `Depends(require(Permission.JOURNAL_POST))`.

---

## 10. Audit trail — **CRITICAL**

The audit trail is our defensibility. It must be trustworthy. Violate these rules and we lose SOC2.

### 10.1 What gets logged

**Every** create/update/delete on any business entity. Plus: logins, failed logins, role changes, period opens/closes, export downloads, AI tool executions that mutate, impersonations.

### 10.2 Schema (simplified)

```
audit_events (
  id              uuid primary key,
  tenant_id       uuid not null,
  occurred_at     timestamptz not null,
  actor_type      text not null,   -- 'user'|'system'|'ai'|'integration'
  actor_id        uuid,
  session_id      uuid,
  ip              inet,
  user_agent      text,
  action          text not null,   -- 'journal.post','period.close',...
  entity_type     text not null,
  entity_id       uuid,
  before          jsonb,           -- null on create
  after           jsonb,           -- null on delete
  metadata        jsonb not null default '{}',
  prev_hash       bytea not null,  -- hash of previous event for this tenant
  hash            bytea not null   -- sha256(prev_hash || canonical_json(this))
)
```

### 10.3 Rules

1. **Append-only**. No `UPDATE`, no `DELETE`. Enforced by a Postgres trigger that raises on non-INSERT.
2. **Hash chain per tenant**. Every event references the previous event's hash. Breakage is a P0.
3. **Writing the audit event is part of the transaction** that performs the business change. If the audit write fails, the business write rolls back.
4. **Never write audit events from the API layer.** They come from domain events emitted by the service layer, consumed by `app.audit`.
5. **No PII in free-text fields.** The `before`/`after` diff auto-redacts fields marked `@pii` in the ORM.
6. **Retention**: 7 years minimum (regulatory). Cold storage after 18 months.

### 10.4 Verification

A background job (daily) walks the hash chain per tenant and alerts on any break. The auditor workspace shows chain verification status.

---

## 11. AI integration guidelines

The AI assistant is a first-class feature, not a toy. Treat it with the same rigor as the ledger.

### 11.1 Models

- Default chat: **Claude Sonnet 4.6** (`claude-sonnet-4-6`)
- Deep analysis / complex reconciliations: **Claude Opus 4.6** (`claude-opus-4-6`)
- Fast classifiers (transaction categorization, receipt parsing triage): **Claude Haiku 4.5** (`claude-haiku-4-5-20251001`)
- Vision (receipt OCR): Sonnet 4.6 or Opus 4.6 with image input.

### 11.2 Prompt caching — **MUST USE**

Every assistant call includes a system prompt + a tenant context block (chart of accounts, recent transactions summary, period status). Both are cached:

```python
messages.create(
    model="claude-sonnet-4-6",
    system=[
        {"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}},
        {"type": "text", "text": tenant_context, "cache_control": {"type": "ephemeral"}},
    ],
    tools=TOOLS,  # tool definitions are also cache-eligible in the system block
    messages=conversation,
)
```

Target **>70% cache hit rate** on system + tenant context. Monitor `cache_creation_input_tokens` vs `cache_read_input_tokens` in Sentry.

### 11.3 Tool use — contract

All tools are defined in `app/ai/tools/` with strict JSON schemas. Tools split into:

- **Read tools** — idempotent, cheap, no confirmation needed.
  Examples: `get_account_balance`, `list_journal_entries`, `get_period_status`, `search_transactions`.
- **Draft tools** — produce a proposal; **do not mutate**. AI calls these freely.
  Examples: `draft_journal_entry`, `draft_reconciliation_match`, `draft_invoice`.
- **Mutation tools** — wrapped in a human-in-the-loop. The AI requests; the UI shows a diff; a user with the right role confirms. Only then does the tool execute.
  Examples: `post_journal_entry`, `approve_bill`, `close_period`.

**NEVER** let the AI call a mutation tool without explicit user confirmation in the current session. There is no "auto-approve." This is enforced in `ai/orchestrator.py` — mutation tools return a "confirmation_required" pseudo-result until confirmed.

### 11.4 Grounding and citations

Claude must cite sources for any factual claim about the ledger. A "source" is one of:

- A journal entry ID
- A transaction ID
- A source document ID
- A report snapshot ID

Responses without citations for factual claims are logged as low-confidence and surfaced to the user as "verify before use."

**NEVER** let the AI invent account names, account codes, counterparty names, or numeric values. If data isn't retrieved via a tool, it must not appear in the response. Include an explicit instruction to this effect in the system prompt, and run a post-hoc validator that scans responses for unreferenced numbers and flags them.

### 11.5 Safety & privacy

- Strip PII (email, phone, SSN, bank account) from conversation logs before persisting. The raw conversation is encrypted at rest and has a 90-day retention.
- Prompt-injection defense: user-supplied text (invoice descriptions, memos) is always wrapped in `<user_content>…</user_content>` tags with an explicit instruction that nothing inside is a directive.
- Rate limits: token-bucket per tenant (10k tokens/min baseline, configurable). Per-user: 50 messages/min.
- Cost guardrails: hard cap on daily tokens per tenant; soft warning at 70%.

### 11.6 Evaluation

Before shipping any prompt change:

1. Run the `ai-evals/` suite (golden questions, expected tool sequences, expected citations).
2. Compare hit/miss deltas vs baseline. Regressions block merge.
3. Eval runs log to `ai_eval_runs` table for historical tracking.

### 11.7 Versioning

- System prompts live in `app/ai/prompts/*.md` and are imported via a loader that records `prompt_version` on every message.
- Tool schemas are versioned; breaking changes require a new tool name (`post_journal_entry_v2`).

---

## 12. Security & compliance

Targets: **SOC 2 Type II**, **ISO 27001**, **GDPR**, **SOX-adjacent controls for customers who need them**.

- **Secrets**: env vars via Doppler/1Password Connect in prod. `.env.example` only in repo. Scan with `gitleaks` in CI.
- **TLS 1.3** everywhere. HSTS, CSP, `X-Content-Type-Options: nosniff`, `Referrer-Policy: same-origin`.
- **Password hashing**: Argon2id, time=3, memory=64MiB, parallelism=4.
- **Session management**: short-lived JWTs (15m) + rotating refresh (30d, single-use). Revocation list in Redis.
- **MFA**: TOTP (RFC 6238) + WebAuthn. Required for `owner`, `admin`, `auditor`.
- **PII encryption at rest**: column-level AES-GCM via `pgcrypto` for `users.email`, `contacts.*_sensitive`, bank account numbers.
- **Audit log immutability**: see §10.
- **Dependency scanning**: `pip-audit`, `npm audit`, Snyk in CI. P0 CVEs block merge.
- **Static analysis**: Bandit (Python), Semgrep (cross-language).
- **Backups**: Postgres continuous WAL to S3, 30-day PITR, quarterly restore drills.
- **Data residency**: tenant-level region pinning (US / EU / APAC). Enforced by tenant-region routing.

---

## 13. Mobile sync architecture

The mobile app is **offline-first**. Users can create invoices, capture receipts, approve bills without a connection.

### 13.1 Local store

- `op-sqlite` encrypted with a device-bound key (derived from Keychain/Keystore + user PIN).
- Schema mirrors a subset of server tables (accounts, recent transactions, drafts, attachments).

### 13.2 Sync protocol

1. **Pull**: `GET /v1/sync/pull?cursor=<vector_clock>` returns entities changed since cursor + a new cursor.
2. **Push**: `POST /v1/sync/push` with a batch of local mutations, each including `client_op_id` (idempotency key), `base_version`, and the new state.
3. **Server** applies each mutation transactionally:
   - If `base_version` matches current version → apply, bump version, return `applied`.
   - If mismatch → return `conflict` with server state; client resolves per rules below.
4. **Conflict resolution**:
   - **Drafts** (invoices not yet posted, receipts not yet linked): last-writer-wins by client timestamp, loser's copy kept as a local "conflict draft" for user review.
   - **Posted journal entries**: server always wins (they're immutable from mobile).
   - **Approvals**: reject the stale approval, surface "please refresh" to the user.
5. **Push notifications** for: approvals awaiting you, reconciliation mismatches, AI-flagged anomalies, period-close reminders.

### 13.3 Offline UX rules

- Every mutable screen shows a sync status chip (synced / pending / conflict).
- Receipts captured offline are queued with full image; compression happens before upload on cellular.
- Auth: biometric unlock re-uses the last refresh token (encrypted) if within 30 days; otherwise forces re-login.

---

## 14. Testing standards

Coverage targets: **backend 80%**, **web 70%**, **mobile 60%**. Treated as a floor, not a ceiling. 100% on `app.domain.money` and `app.domain.ledger`.

### 14.1 Tiers

- **Unit** (`tests/unit/`): pure domain logic. No DB, no network. Run in < 5s total.
- **Integration** (`tests/integration/`): hit a real Postgres (via testcontainers) and real Redis. **Never mock the database.** (We got burned by a mocked-migration bug; integration tests must exercise the real schema.)
- **Contract** (`tests/contract/`): API responses validated against OpenAPI spec; generated clients validated against server.
- **Property** (`tests/property/`): Hypothesis tests for money math, FX conversion, journal balancing. Every invariant listed in §8 has at least one property test.
- **E2E**: Playwright (web), Detox (mobile). Run nightly + on release branch.

### 14.2 Rules

- Every new endpoint: happy path + 3 failure cases (auth, validation, tenant isolation).
- Every new migration: up + down + `alembic check` in CI.
- Every new tool exposed to AI: schema test + at least one golden eval.
- Tests set their own tenant context; don't rely on global state.

---

## 15. Performance guidelines

- **API p99 target**: 300 ms (excluding AI streaming endpoints).
- **Lists**: always paginated, `limit` max 200, default 50. Cursor-based for infinite scroll.
- **Reports**: pre-aggregated via materialized views refreshed incrementally; queries read views, never raw ledger.
- **Large exports (> 5k rows)**: enqueue ARQ job, email link when ready. No synchronous > 30s responses.
- **AI responses**: stream via SSE. First token target < 800 ms.
- **Mobile bundle**: < 40 MB download on Android, < 80 MB IPA. Assets lazy-loaded.
- **DB**: EXPLAIN ANALYZE every query that touches a table > 100k rows before merging. Index if sequential scan + high cost.

---

## 16. Commands reference

```bash
# Setup
make bootstrap                # install everything
make up / make down           # start/stop local services

# DB
make migrate                  # apply migrations
make migrate-down n=1         # roll back n migrations
make migration m="<desc>"     # generate new migration
make seed                     # reset + seed demo data
make db-shell                 # psql into local db

# Dev
make dev                      # run api + web + mobile metro in parallel
make api / make web / make mobile   # run individually

# Quality
make test                     # fast tests
make test-slow                # integration + e2e
make lint                     # all linters
make fix                      # auto-fix
make typecheck                # mypy + tsc
make coverage                 # coverage report

# AI
make ai-evals                 # run AI evaluation suite
make ai-evals-diff            # compare current run to baseline

# Release
make openapi                  # export OpenAPI spec to docs/
make client-gen               # regenerate TS client from OpenAPI
```

If a command doesn't exist, **create it in the Makefile rather than document a bespoke incantation.**

---

## 17. Common pitfalls — **read this before starting**

1. **Using `float` for money.** See §8. If you see it in legacy code, fix it; don't add more.
2. **Forgetting `tenant_id`.** RLS will block you, but the error message is confusing. Set it in the session early.
3. **Bypassing the audit log.** If you write to a ledger table without going through a service method, no audit event is emitted. **Always go through the service.**
4. **Letting the AI hallucinate.** If data comes from model output and not a tool call, treat it as untrusted text, never as facts.
5. **Naive datetimes.** Always `datetime.now(tz=timezone.utc)` on the backend; always ISO-8601 with offset in JSON. Postgres columns are `timestamptz`, never `timestamp`.
6. **Updating a `hard_closed` period.** You can't. If you think you need to, you actually need to open a reversing entry in the current period.
7. **Amending published commits.** Create a new commit. The hook is there for a reason.
8. **Swallowing exceptions.** Log + re-raise + add context. A silent except is worse than a crash.
9. **Committing secrets.** `gitleaks` will catch most; the `.env.example` file is the canonical list of what's needed.
10. **Trusting `tenant_id` from the request body.** See §9.
11. **Writing comments that restate the code.** Don't. Write tests instead.
12. **Creating `*_v2.py` files when refactoring.** Refactor in place. Old code is deleted, not archived.

---

## 18. Escalation — when to ask the user

Stop and ask **before** doing any of these:

- Changing a locked tech-stack choice (§4).
- Touching the audit trail schema, hash chain, or tenant isolation mechanism.
- Dropping or renaming an existing migration.
- Changing money rounding, scale, or currency handling.
- Adding a new AI tool that mutates data — especially one that could move money.
- Granting broader permissions to an existing role.
- Adding a dependency with a non-permissive license.
- Any action that touches production data or third-party APIs with real side effects.

A 30-second "I'm about to do X, confirming?" prevents an afternoon of rollback.

---

## 19. Glossary (quick)

| Term | Meaning |
|------|---------|
| GL   | General Ledger — the master record of all journal entries |
| JE   | Journal Entry — a balanced set of debits and credits |
| COA  | Chart of Accounts — the list of accounts per tenant |
| AR/AP| Accounts Receivable / Payable |
| P&L  | Profit and Loss (Income Statement) |
| BS   | Balance Sheet |
| CF   | Cash Flow Statement |
| FX   | Foreign Exchange |
| RLS  | Row-Level Security (Postgres) |
| PITR | Point-in-Time Recovery |
| TB   | Trial Balance |

For the full product scope, feature roadmap, and phase-by-phase execution plan: **`docs/PRP.md`**.
