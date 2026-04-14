# Aegis ERP — Product Requirements Plan (PRP)

> **Purpose.** This document is the single source of truth for *what* Aegis ERP is and *how we will build it, phase by phase*. It is written so that an autonomous coding agent (e.g., Claude Sonnet) can execute it end-to-end by working through the phases in order, checking off acceptance criteria as it goes.
>
> **Companion doc:** `CLAUDE.md` in the repo root describes *how* to code — conventions, rules, rails. The PRP describes *what* to code and *when*. Read `CLAUDE.md` first; it is binding.

---

## 0. How an agent should execute this plan

**You are a coding agent picking up this repo.** Follow this loop:

1. Read `CLAUDE.md` fully. Honor every MUST/NEVER.
2. Read this PRP section 1–8 for context.
3. Go to **§9 Phased Implementation**. Find the lowest-numbered phase whose **Exit Criteria** are not all green.
4. Inside that phase, find the lowest-numbered task whose status in §10 *Execution Tracker* is not `done`.
5. Implement the task. Write tests as specified. Run the verification commands in the task's **Definition of Done**.
6. Update the Execution Tracker entry to `done` + commit. Open a PR (one PR per task unless the task explicitly says to bundle).
7. If blocked, add a **Blocker** entry to §11 with: what you tried, what failed, what decision is needed. Stop and ask the user.
8. **Never skip a phase's Exit Criteria.** Phases are gates, not suggestions.

Rules:

- **Small PRs.** One task = one PR unless the task says otherwise. Keep diffs reviewable.
- **Tests are part of the task**, not a follow-up. A task without tests is not done.
- **Acceptance criteria are literal.** If a criterion says "returns 422 for invalid currency," write a test that asserts exactly that.
- **Don't expand scope.** If you notice something adjacent that should also change, open an issue or add it to §12 *Parking Lot*. Don't silently do it.
- **Ask before changing locked decisions** (tech stack, audit trail design, money rules, tenant isolation).

---

## 1. Executive summary

Aegis ERP is a cloud-first, AI-native accounting + light-ERP platform in the Xero/QuickBooks Online class, differentiated by three things:

1. **An embedded Claude assistant** that can reason over the live ledger, draft journal entries, surface anomalies, and answer audit questions — with citations and human-in-the-loop mutations.
2. **An audit-first posture.** Tamper-evident audit trail, a dedicated auditor workspace, and one-click evidence packages for SOX / ISO / internal audit requests.
3. **A true mobile companion.** Offline-first Expo app for capture, approval, and review, with deterministic sync.

The V1 target customer is small-to-mid businesses with 10–500 employees in services, e-commerce, or light wholesale — markets where Xero dominates but AI/audit are weak spots.

---

## 2. Vision, goals, non-goals

### 2.1 Vision
*"An accountant's accountant: the books are right, the audit trail is airtight, and the AI does the boring 80% — without ever inventing a number."*

### 2.2 12-month goals

- **Ship a Xero-feature-parity MVP** for core accounting (GL, AR, AP, bank rec, reporting, tax).
- **Ship an AI assistant** that handles 50% of bookkeeping questions and drafts 80% of routine journals for review.
- **Ship an auditor workspace** that reduces average audit request turnaround from days to hours.
- **Ship a mobile app** (iOS + Android) with offline capture, approvals, and read access.

### 2.3 Explicit non-goals (V1)

- **Manufacturing / MRP / BOM.** We are not SAP.
- **Full payroll.** We integrate with Gusto/Rippling/Deel; we don't run payroll.
- **Crypto accounting.** Out of scope; revisit if market pulls.
- **Industry-specific modules** (construction, healthcare, etc.) — come after V1.
- **Plugin marketplace / third-party app store** — Phase 7+, not earlier.
- **On-prem deployment.** Cloud multi-tenant only.
- **Direct competition with full ERPs.** We are "Xero plus AI plus mobile plus audit," not NetSuite.

---

## 3. Target users & personas

### 3.1 Priya — "The bookkeeper"
- Runs books for 6–15 small businesses.
- Pain: shuttling between Xero, email, receipts apps, spreadsheets; chasing clients for docs.
- Must-have: bulk operations, keyboard shortcuts, "AI drafted this, approve?", client portal.

### 3.2 Marco — "The operator"
- SMB owner, 40-person services firm. Checks dashboards Monday mornings.
- Pain: doesn't trust numbers; approvals pile up; receipts go missing.
- Must-have: mobile approvals, a weekly AI summary he can actually read, receipt capture.

### 3.3 Asha — "The controller"
- In-house accountant at a 200-person e-comm firm.
- Pain: month-end close takes 8 days; audit requests eat her January.
- Must-have: period close workflow, variance explanations, audit workspace, pre-built evidence packs.

### 3.4 Eli — "The auditor"
- External auditor at a Big-4 firm.
- Pain: clients send zip files of JPGs; sampling is manual; trail verification is manual.
- Must-have: auditor workspace (read-only, scoped), evidence package export, hash-chain verification dashboard.

Every feature must trace to at least one persona's job-to-be-done. If it doesn't, cut it.

---

## 4. Success metrics

### 4.1 North Star
**Active Verified Ledgers** — number of tenants whose audit-chain verification passed in the last 7 days AND who had ≥ 10 posted journals in the last 7 days. Counts usage *and* data integrity in one number.

### 4.2 Guardrail metrics (alert if these regress)

| Metric | Target | Alarm at |
|--------|--------|----------|
| Audit hash-chain continuity | 100% of tenants | any break |
| API p99 latency | < 300 ms | > 500 ms |
| AI tool-call accuracy (evals) | > 95% | < 92% |
| AI citation coverage | > 98% of factual claims cited | < 95% |
| Mobile sync conflict rate | < 0.5% of ops | > 1% |
| Money precision test suite | 100% pass | any fail |
| Tenant isolation test suite | 100% pass | any fail |

### 4.3 Product metrics (track and optimize)

- Time-to-first-journal after signup.
- % of month-end closes completed in ≤ 5 business days.
- AI assistant weekly-active usage per tenant.
- Audit-request-to-evidence-pack cycle time.
- Mobile DAU / Web DAU ratio.

---

## 5. Product pillars (expanded)

### 5.1 Pillar A — Core Ledger (Phases 1–2)
Feature-parity with Xero for the core accounting loop: CoA, journals, AR, AP, bank rec, tax, period close, standard reports. Correct-by-construction (double-entry, RLS, audit-on-mutate).

### 5.2 Pillar B — AI Assistant (Phase 3)
A Claude-powered chat anchored to the tenant's live data. Read tools for Q&A, draft tools for proposals, mutation tools with human confirmation. Always cites. Never invents.

### 5.3 Pillar C — Audit Module (Phase 4)
An auditor-only workspace: read-only scoped access, sampling tools, evidence-package builder, hash-chain verification dashboard, standard audit reports (GL detail, JE testing, cutoff testing).

### 5.4 Pillar D — Mobile Companion (Phase 5)
Offline-first Expo app for capture (receipts, expense claims), approval (bills, expense claims), and review (dashboards, recent activity). Biometric unlock, push for approvals.

### 5.5 Pillar E — ERP Extensions (Phase 6+)
Inventory, projects, advanced multi-entity, integrations marketplace. Layered on the core; not required for MVP.

---

## 6. Master feature map

Legend: **P0** = MVP blocker. **P1** = V1 (12 months). **P2** = V1.5. **P3** = later.

### 6.1 Platform

| ID | Feature | Priority | Phase |
|----|---------|----------|-------|
| PLAT-01 | Tenant provisioning & onboarding wizard | P0 | 0 |
| PLAT-02 | User invites, roles, permissions | P0 | 0 |
| PLAT-03 | MFA (TOTP + WebAuthn) | P0 | 0 |
| PLAT-04 | SSO (OIDC, SAML) | P1 | 6 |
| PLAT-05 | Billing & subscriptions (Stripe) | P1 | 6 |
| PLAT-06 | Audit log (write side) | P0 | 0 |
| PLAT-07 | Audit log verification daemon | P0 | 4 |
| PLAT-08 | Feature flags | P1 | 0 |
| PLAT-09 | Tenant region pinning | P1 | 6 |
| PLAT-10 | Data export (GDPR) | P0 | 4 |
| PLAT-11 | Tenant deletion & data retention | P1 | 6 |

### 6.2 Core accounting

| ID | Feature | Priority | Phase |
|----|---------|----------|-------|
| ACC-01 | Chart of Accounts (CRUD, hierarchy, templates) | P0 | 1 |
| ACC-02 | Journal entries (manual, recurring, reversing) | P0 | 1 |
| ACC-03 | Periods & period close (open/soft/hard/audited) | P0 | 1 |
| ACC-04 | Multi-currency + FX rates (daily feed) | P0 | 1 |
| ACC-05 | Tax codes & tax rates (multi-jurisdiction) | P0 | 2 |
| ACC-06 | Contacts (customers/suppliers/employees) | P0 | 2 |
| ACC-07 | Items (products & services) | P0 | 2 |
| ACC-08 | Invoicing (AR): draft, send, void, credit note | P0 | 2 |
| ACC-09 | Bills (AP): draft, approve, pay, credit note | P0 | 2 |
| ACC-10 | Payments: receipts, disbursements, batching | P0 | 2 |
| ACC-11 | Bank accounts & bank feeds (Plaid/TrueLayer) | P0 | 2 |
| ACC-12 | Bank reconciliation (manual + AI-assisted match) | P0 | 2 |
| ACC-13 | Expense claims (employee + receipt) | P0 | 2 |
| ACC-14 | Period-end revaluation & closing journals | P0 | 2 |
| ACC-15 | Intercompany & consolidation | P2 | 6 |
| ACC-16 | Budgeting & forecasts | P2 | 6 |

### 6.3 Reporting

| ID | Feature | Priority | Phase |
|----|---------|----------|-------|
| RPT-01 | Trial Balance | P0 | 1 |
| RPT-02 | General Ledger detail | P0 | 1 |
| RPT-03 | Profit & Loss (Income Statement) | P0 | 2 |
| RPT-04 | Balance Sheet | P0 | 2 |
| RPT-05 | Cash Flow Statement (indirect) | P1 | 2 |
| RPT-06 | AR / AP aging | P0 | 2 |
| RPT-07 | Tax summary (e.g. BAS/VAT/GST return prep) | P0 | 2 |
| RPT-08 | Custom report builder | P2 | 6 |
| RPT-09 | Saved views & scheduled emails | P1 | 6 |
| RPT-10 | Report snapshots (immutable, signed) | P0 | 4 |

### 6.4 AI capabilities

| ID | Feature | Priority | Phase |
|----|---------|----------|-------|
| AI-01 | Chat interface (streaming, history, tenant-scoped) | P0 | 3 |
| AI-02 | Read tools (balances, transactions, periods, reports) | P0 | 3 |
| AI-03 | Draft tools (journal, invoice, reconciliation match) | P0 | 3 |
| AI-04 | Mutation tools with human confirmation | P0 | 3 |
| AI-05 | Receipt OCR + auto-categorization | P0 | 3 |
| AI-06 | Anomaly detection (duplicate, outlier, unusual pattern) | P1 | 3 |
| AI-07 | Natural-language report generation | P1 | 3 |
| AI-08 | Month-end close assistant (checklist + variance exp) | P1 | 3 |
| AI-09 | Audit Q&A ("explain this entry" with citations) | P0 | 4 |
| AI-10 | Eval harness + regression gating | P0 | 3 |
| AI-11 | Prompt caching + cost observability | P0 | 3 |
| AI-12 | Per-tenant AI feature flags + spend caps | P0 | 3 |

### 6.5 Audit module

| ID | Feature | Priority | Phase |
|----|---------|----------|-------|
| AUD-01 | Auditor role + scoped workspace | P0 | 4 |
| AUD-02 | Audit timeline (search/filter events) | P0 | 4 |
| AUD-03 | Hash-chain verification dashboard | P0 | 4 |
| AUD-04 | Sampling tool (random, MUS, stratified) | P0 | 4 |
| AUD-05 | Evidence package builder (PDF + JSON + hash manifest) | P0 | 4 |
| AUD-06 | Journal-entry testing reports (JE cutoff, unusual) | P0 | 4 |
| AUD-07 | Audit request workflow (intake, respond, sign-off) | P1 | 4 |
| AUD-08 | External auditor invites (time-scoped) | P0 | 4 |
| AUD-09 | Segregation-of-duties checks | P1 | 6 |

### 6.6 Mobile

| ID | Feature | Priority | Phase |
|----|---------|----------|-------|
| MOB-01 | Auth, biometric unlock, PIN fallback | P0 | 5 |
| MOB-02 | Offline store + sync engine | P0 | 5 |
| MOB-03 | Receipt capture (camera, crop, upload) | P0 | 5 |
| MOB-04 | Expense claim creation | P0 | 5 |
| MOB-05 | Approvals inbox (bills, expense claims) | P0 | 5 |
| MOB-06 | Dashboard widgets (cash, AR, AP, alerts) | P0 | 5 |
| MOB-07 | Recent transactions, search | P0 | 5 |
| MOB-08 | Push notifications | P0 | 5 |
| MOB-09 | Embedded AI chat (voice input) | P1 | 5 |
| MOB-10 | Deep linking (from push to entity) | P0 | 5 |

### 6.7 Integrations (Phase 6–7)

| ID | Integration | Priority |
|----|-------------|----------|
| INT-01 | Plaid / TrueLayer (bank feeds) | P0 |
| INT-02 | Stripe (payments in) | P1 |
| INT-03 | Gusto / Deel / Rippling (payroll) | P1 |
| INT-04 | Shopify / WooCommerce (sales) | P1 |
| INT-05 | Google Drive / Dropbox (doc attach) | P2 |
| INT-06 | Slack / Teams (notifications) | P2 |
| INT-07 | OIDC / SAML IdPs | P1 |
| INT-08 | Public REST API + webhooks | P1 |
| INT-09 | OAuth app directory | P2 |

---

## 7. Technical architecture

### 7.1 System components
See `CLAUDE.md §3` for the ASCII diagram. Summary:

- Single FastAPI monolith (`backend/`) with internal module boundaries (ledger, ai, audit, sync, tenant).
- Postgres 16 (primary), Redis (cache + queue), S3-compatible object store.
- Workers (ARQ) for: bank feed sync, AI async jobs, report generation, evidence packaging, audit verification.
- Web app (Next.js) and Mobile app (Expo) talk to the same `/v1` REST API + SSE for streaming AI.

### 7.2 Service boundaries (internal)

| Module | Owns | Depends on |
|--------|------|------------|
| `tenant` | orgs, users, roles, sessions | — |
| `ledger` | COA, JE, period, FX | `tenant`, `money` |
| `money` | Money type, FX math | — |
| `accounts_rx` | Invoices, customer payments | `ledger`, `tenant` |
| `accounts_px` | Bills, vendor payments | `ledger`, `tenant` |
| `banking` | Bank accounts, feeds, reconciliation | `ledger`, `accounts_rx`, `accounts_px` |
| `tax` | Tax codes, tax returns | `ledger` |
| `reporting` | Materialized views, report generation | `ledger` |
| `audit` | Event sink, hash chain, verification | all (as observer) |
| `ai` | Claude orchestrator, tools, prompts | all (as client) |
| `sync` | Mobile sync, delta protocol | all (as observer/writer) |
| `docs` | Attachments, OCR metadata | `tenant` |

Cross-module: emit domain events; never import sibling services directly.

### 7.3 Data model — high-level ERD

Core entities (non-exhaustive, all have `tenant_id`, `id`, `created_at`, `updated_at`, `version`):

```
tenants ──< users (m:n via memberships)
tenants ──< chart_of_accounts ──< accounts (hierarchy via parent_id)
tenants ──< periods ──< journal_entries ──< journal_lines >── accounts
tenants ──< contacts (customer|supplier|employee)
tenants ──< items
tenants ──< invoices ──< invoice_lines >── items, contacts
tenants ──< bills ──< bill_lines >── items, contacts
tenants ──< payments ──< payment_allocations >── invoices|bills
tenants ──< bank_accounts ──< bank_statement_lines ──< matches >── journal_entries
tenants ──< tax_codes ──< tax_rates (effective-dated)
tenants ──< documents (attachments, OCR payloads)
tenants ──< audit_events (append-only, hash-chained)
tenants ──< ai_conversations ──< ai_messages ──< ai_tool_calls
```

Explicit constraints (must appear in migrations):

- `journal_lines.journal_entry_id FK ON DELETE CASCADE`
- `journal_entries` has `CHECK (debit_total = credit_total)` (enforced at app layer across lines; DB enforces via trigger)
- `periods.status CHECK IN ('open','soft_closed','hard_closed','audited')`
- `audit_events` insert-only trigger; `prev_hash`/`hash` NOT NULL
- Every tenant-scoped table: `CREATE POLICY tenant_isolation`
- Money columns: `NUMERIC(19,4) NOT NULL` + `currency CHAR(3) NOT NULL`

### 7.4 API surface (high-level)

Versioned under `/v1`. REST + JSON. OpenAPI auto-generated. WebSocket/SSE only for AI streaming and realtime notifications.

Domains (one router per):

```
/v1/auth          login, refresh, mfa, password reset
/v1/tenants       current tenant, settings
/v1/users         profile, preferences, sessions
/v1/memberships   invites, roles
/v1/accounts      chart of accounts
/v1/journals      journal entries
/v1/periods       periods + close workflow
/v1/contacts      customers, suppliers, employees
/v1/items         products & services
/v1/invoices      AR
/v1/bills         AP
/v1/payments      in/out
/v1/bank          accounts, feeds, reconciliation
/v1/tax           codes, rates, returns
/v1/reports       P&L, BS, CF, TB, GL, aging, tax summary
/v1/documents     attachments + OCR
/v1/audit         events, chain verification, evidence packages
/v1/ai            conversations, messages (SSE), tool confirmations
/v1/sync          pull, push (mobile)
/v1/integrations  connect/disconnect, webhook receivers
/v1/admin         tenant-owner-only ops
```

Conventions:

- `POST` returns created resource with `Location` header.
- `PATCH` for partial updates with `If-Match` header carrying `version`; 409 on mismatch.
- Pagination: `?limit=50&cursor=<opaque>`. Response includes `next_cursor`.
- Filtering: `?filter[status]=open&filter[date_from]=…`
- Errors: RFC 9457 Problem Details (`application/problem+json`).
- Idempotency: `Idempotency-Key` header on all state-changing POSTs.

### 7.5 AI architecture

See `CLAUDE.md §11`. In addition:

- **Conversation state** stored in Postgres; token-level message history never exceeds 40k tokens before compaction (summarize oldest turns with Haiku into a single system-role message).
- **Tool execution engine** (`app/ai/orchestrator.py`) is a state machine: `awaiting_model → tool_call_pending → tool_executed | awaiting_user_confirmation → …`
- **Response validator** (post-hoc) scans the final assistant message for numeric tokens or account names not present in tool outputs; flags them.
- **SSE protocol** streams deltas as `data:` events with types: `text_delta`, `tool_use`, `tool_result`, `confirm_required`, `done`, `error`.

### 7.6 Mobile sync protocol

See `CLAUDE.md §13`. Additional specifics:

- Cursor format: `v1.<tenant_id>.<lamport_clock>`. Opaque to client.
- Push batch size: max 200 ops.
- Attachment upload: two-phase — (1) request pre-signed S3 URL, (2) upload, (3) finalize with checksum.
- Background sync every 5 min when app is foreground, opportunistic on push.

### 7.7 Security model

See `CLAUDE.md §12`. Additional:

- **Secret rotation** quarterly; automated for most via Doppler.
- **Threat model**: STRIDE review per phase. Tracked in `docs/security/threat-model.md`.
- **Pen test** before GA and annually after.
- **Bug bounty** via HackerOne from GA.

---

## 8. Domain model — detailed specs

This section defines the shape of key entities. Agents implementing schemas **must match these** unless they escalate a change. Keep Pydantic schemas, SQLAlchemy models, and migrations in sync.

### 8.1 Tenant
```
Tenant
  id: UUIDv7
  name: str
  legal_name: str
  country: ISO-3166-2 (e.g. "US", "AU", "HK")
  functional_currency: ISO-4217  # immutable after first posted entry
  fiscal_year_start_month: 1-12
  timezone: IANA TZ
  region: 'us'|'eu'|'apac'
  status: 'trial'|'active'|'suspended'|'closed'
  created_at, updated_at, version
```

### 8.2 User & membership
```
User
  id, email (unique, lowercased), display_name, locale
  password_hash (Argon2id)
  mfa_totp_secret (encrypted), webauthn_credentials[]
  email_verified_at
  last_login_at, login_failure_count
Membership
  id, user_id, tenant_id, role: enum, status: 'invited'|'active'|'suspended'
  invited_by, invited_at, joined_at
Session
  id, user_id, refresh_token_hash, ip, user_agent, expires_at
```

### 8.3 Account (Chart of Accounts)
```
Account
  id, tenant_id
  code: str (e.g. "1000")
  name: str
  type: 'asset'|'liability'|'equity'|'revenue'|'expense'
  subtype: enum (e.g. 'current_asset','long_term_liability')
  normal_balance: 'debit'|'credit'
  parent_id: Account nullable
  is_active: bool
  is_system: bool   # cannot be edited/deleted (e.g. Retained Earnings)
  currency: ISO-4217 nullable   # null = functional
  tax_code_id: nullable
  description: text nullable
  reporting_tags: string[]
```

Rules:
- `code` unique per tenant.
- Cannot delete if any journal_line references it → deactivate only.
- System accounts (e.g. Accounts Receivable control, Accounts Payable control, Retained Earnings, Suspense) are created on tenant provisioning from a country template.

### 8.4 Period
```
Period
  id, tenant_id
  name: str (e.g. "2026-04")
  start_date, end_date
  status: 'open'|'soft_closed'|'hard_closed'|'audited'
  closed_at, closed_by, closed_reason
  reopened_at, reopened_by, reopened_reason
```

Rules:
- Exactly one `open` period "next." Periods are pre-generated a year ahead.
- Posting requires target period `open` or `soft_closed` (soft allows with admin override + audit).
- `hard_closed` blocks posting even for admins. Reopen requires `auditor` role.

### 8.5 Journal entry
```
JournalEntry
  id, tenant_id
  number: str (tenant-unique, sequence per year)
  date: date
  period_id: FK
  description: text
  source_type: 'manual'|'invoice'|'bill'|'payment'|'bank'|'fx_reval'|'period_close'|'ai_draft'
  source_id: nullable UUID (points to invoice/bill/etc)
  status: 'draft'|'posted'|'void'
  posted_at, posted_by
  void_of: nullable FK (reverses this entry)
  fx_rate_date: date nullable
  total_debit: Decimal(19,4)
  total_credit: Decimal(19,4)
  currency: ISO-4217    # usually functional; multi-currency stored per line
JournalLine
  id, tenant_id, journal_entry_id
  line_no: int (1..n)
  account_id
  contact_id: nullable
  tax_code_id: nullable
  description: text nullable
  debit: Decimal(19,4) default 0
  credit: Decimal(19,4) default 0
  currency: ISO-4217
  fx_rate: Decimal nullable
  functional_debit: Decimal
  functional_credit: Decimal
  tracking: jsonb  # dimensions (department, project, region)
```

Rules (enforced at **all three layers**):
- For each line, exactly one of `debit`/`credit` > 0.
- `sum(debit) = sum(credit)` in functional currency.
- `status='posted'` makes the entry immutable (no updates); corrections go through void+reissue.
- `void_of` entry auto-generated with flipped amounts.

### 8.6 Contact
```
Contact
  id, tenant_id
  kind: 'customer'|'supplier'|'employee'|'other'   # can hold multiple via flags
  display_name, legal_name
  email, phone, website
  tax_id, tax_id_type  # e.g. 'abn','vat','ein'
  default_currency, payment_terms_days, credit_limit
  addresses: Address[] (shipping, billing)
  bank_details: BankDetail[]  # for supplier payments
  status: 'active'|'archived'
```

### 8.7 Item (Product/Service)
```
Item
  id, tenant_id
  sku, name, description
  kind: 'product'|'service'
  sales_unit_price, sales_account_id, sales_tax_code_id
  purchase_unit_price, purchase_account_id, purchase_tax_code_id
  is_inventory_tracked: bool   # Phase 6
  inventory_asset_account_id: nullable
  cogs_account_id: nullable
```

### 8.8 Invoice (AR)
```
Invoice
  id, tenant_id, number, contact_id
  issue_date, due_date
  currency, fx_rate
  status: 'draft'|'submitted'|'authorized'|'sent'|'partially_paid'|'paid'|'void'
  subtotal, tax_total, total
  amount_due
  notes, terms
  sent_at, viewed_at, pdf_document_id
  journal_entry_id  # on authorize
InvoiceLine
  id, invoice_id, line_no
  item_id nullable, description, quantity, unit_price
  discount_percent, tax_code_id, tax_amount
  account_id  # revenue account
  line_total
  tracking: jsonb
```

Lifecycle transitions:
`draft → submitted → authorized (posts JE) → sent → (partially_)paid|void`.
Credit notes reference an invoice and reverse (or partially reverse) via a new JE.

### 8.9 Bill (AP)
Mirror of Invoice with `supplier_id`, `expense/asset` account on lines, approval workflow:
`draft → awaiting_approval → approved (posts JE) → (partially_)paid|void`.

### 8.10 Payment
```
Payment
  id, tenant_id, direction: 'in'|'out'
  contact_id, bank_account_id
  date, reference, amount, currency, fx_rate
  status: 'draft'|'posted'|'void'
  journal_entry_id
PaymentAllocation
  payment_id, target_kind: 'invoice'|'bill'|'credit_note'|'prepayment'
  target_id, amount, currency
```

### 8.11 Bank account & reconciliation
```
BankAccount
  id, tenant_id
  name, currency, account_number_masked, institution, feed_provider, external_id
  gl_account_id   # links to an Asset account in COA
  last_feed_at
BankStatementLine
  id, tenant_id, bank_account_id
  date, description, amount, balance, external_id (idempotent)
  status: 'unmatched'|'proposed'|'matched'|'excluded'
  suggested_match_id  # to a candidate JE/invoice/bill
ReconciliationSession
  id, tenant_id, bank_account_id, opened_at, closed_at, opened_by
  statement_from, statement_to, statement_end_balance
Match
  id, session_id, statement_line_id, journal_entry_id, amount, kind: 'direct'|'split'|'create_new'
```

### 8.12 Tax
```
TaxCode
  id, tenant_id, code, name
  kind: 'sales'|'purchase'|'both'
  is_compound, report_box
  rates: TaxRate[]   # effective-dated
TaxRate
  id, tax_code_id, rate (Decimal), valid_from, valid_to nullable
```

Tax is attached to lines; JE posting splits into gross/net/tax legs using country-template logic.

### 8.13 Document / attachment
```
Document
  id, tenant_id
  kind: 'receipt'|'invoice_pdf'|'bill_pdf'|'statement'|'contract'|'other'
  filename, mime_type, size_bytes, storage_key, checksum_sha256
  ocr_status: 'pending'|'done'|'failed'|'skipped'
  ocr_payload: jsonb   # raw Claude Vision result
  parsed: jsonb        # structured extraction
  linked: [(entity_type, entity_id)]   # many-to-many to business entities
  uploaded_by, uploaded_at
```

### 8.14 Audit event
See `CLAUDE.md §10.2`. Additionally:

- `action` follows dot notation: `journal.post`, `period.close`, `invoice.void`, `ai.tool_call.post_journal_entry`, `auth.login`.
- `metadata` may include `ai_conversation_id`, `approval_chain_id`, `evidence_package_id` as applicable.

### 8.15 AI conversation & tool calls
```
AIConversation
  id, tenant_id, user_id, title, model, prompt_version, created_at, archived_at
AIMessage
  id, conversation_id, role: 'user'|'assistant'|'tool'|'system'
  content: jsonb   # blocks: text, tool_use, tool_result
  input_tokens, output_tokens, cache_read_tokens, cache_creation_tokens, cost_cents
  created_at
AIToolCall
  id, message_id, tool_name, arguments: jsonb, result: jsonb, status: 'pending_confirmation'|'executed'|'rejected'|'error'
  confirmed_by, confirmed_at, audit_event_id nullable
```

### 8.16 Sync
```
SyncDevice
  id, tenant_id, user_id, device_fingerprint, platform, app_version, last_seen, push_token
SyncOp
  client_op_id, device_id, entity_type, entity_id, base_version, new_state, applied_version, status, error, applied_at
```

---

## 9. Phased implementation

Each phase has: **Objective → Scope → Exit Criteria → Task list**. Tasks are granular and atomic: one task ≈ one PR.

---

### **Phase 0 — Foundation (Weeks 1–2)**

**Objective.** Stand up the repo, CI, local dev, identity, multi-tenancy, and the audit infrastructure. Nothing user-visible yet; everything below builds on this.

**Exit criteria.**
- [ ] `make bootstrap && make up && make test` passes on a clean clone.
- [ ] Postgres with RLS enabled. Attempt to cross-tenant query returns zero rows.
- [ ] Audit log receives an event for every mutation in the test suite; hash chain verifies.
- [ ] CI green: lint + typecheck + test + migration check + security scans.
- [ ] A dev can sign up, log in (with MFA TOTP), invite a teammate, and see an audit event for each action.

**Tasks.**

- **T0.1** Initialize monorepo scaffolding: `backend/`, `frontend/apps/{web,mobile}`, `frontend/packages/{ui,api-client,money,types}`, `docs/`, `infra/`, `scripts/`. Add root `Makefile` with stub targets.
  - DoD: `tree -L 3` matches §5 structure. `make` prints available targets.
- **T0.2** Backend: `pyproject.toml`, Ruff, Black, Mypy strict, pytest. Minimal FastAPI app with `/healthz`.
  - DoD: `make test` passes with one smoke test. `make lint` clean.
- **T0.3** Docker Compose: Postgres 16, Redis 7, MinIO, Mailhog. `.env.example`. `make up/down` works.
  - DoD: `docker compose ps` shows all healthy.
- **T0.4** Alembic setup + base migration (uuid extension, initial schema with `tenants`, `users`, `memberships`, `sessions`, `audit_events`).
  - DoD: `make migrate` applies cleanly; `alembic downgrade -1 && upgrade head` works.
- **T0.5** Core: config via Pydantic Settings; structlog; OpenTelemetry; Sentry init (gated by env).
  - DoD: Log lines are JSON with `trace_id`; Sentry captures a test exception in dev.
- **T0.6** Money module (`app/domain/money/`) implementing `Money` value object, `Currency` enum, arithmetic, rounding, JSON ser/de. Zero-dep except `decimal`. 100% unit + property tests.
  - DoD: Coverage 100%. Property tests include associativity, identity, currency-mismatch errors, no float roundtrip.
- **T0.7** Multi-tenancy primitives: `tenant_id` context var + middleware; SQLAlchemy event to enforce tenant filter; Postgres RLS helper `SET LOCAL app.tenant_id=…` per request.
  - DoD: Integration test `test_tenant_isolation.py` creates two tenants and asserts zero leakage across all CRUD paths.
- **T0.8** Auth: signup/login/logout, password hashing (Argon2id), JWT access + rotating refresh, email verification tokens, password reset.
  - DoD: Endpoint tests cover success + 5 failure modes each. Tokens short-lived; refresh rotates.
- **T0.9** MFA: TOTP enrollment + verification; WebAuthn (registration + assertion). Required for `owner`/`admin` after first login.
  - DoD: End-to-end flow test (enroll, login requires code, recovery codes work).
- **T0.10** RBAC: roles enum + permissions registry + `Depends(require(Permission.X))`. Role assignment via membership.
  - DoD: Matrix test: every (role, permission) cell matches spec.
- **T0.11** Audit log write-side: SQLAlchemy event listeners on `after_insert/update/delete` of any tenant-scoped model emit `audit_events` in the **same transaction**. Hash chain per tenant computed and stored.
  - DoD: Unit tests: hash of next = sha256(prev_hash || canonical_json(event)). Integration: every mutation across auth + membership + tenant produces exactly one event.
- **T0.12** Audit log append-only Postgres trigger (block UPDATE/DELETE on `audit_events`).
  - DoD: Attempting update or delete from psql raises error; migration covers trigger.
- **T0.13** Tenant onboarding: create tenant → seed country-specific CoA template + default tax codes + system accounts.
  - DoD: Templates for US, AU, UK, HK, SG committed under `backend/app/infra/templates/`. Test: provisioning a US tenant yields 80+ accounts with correct types.
- **T0.14** User invites: create/accept/revoke, tokenized links, expiry.
  - DoD: Invite email sent (to Mailhog in dev). Accept flow tested.
- **T0.15** Feature flags: simple table + per-tenant overrides + `is_enabled("flag", tenant)` helper.
  - DoD: Used by at least one conditional path; admin endpoint to toggle works.
- **T0.16** Observability: tracing auto-instrumentation (FastAPI, SQLAlchemy, httpx); per-request log context with `request_id`, `tenant_id`, `user_id`.
  - DoD: Test: a traced request shows spans across endpoint → service → repo.
- **T0.17** CI pipeline (GitHub Actions): lint + typecheck + unit + integration (w/ service containers) + migration-up-then-down check + `pip-audit` + `gitleaks` + `bandit` + `semgrep`.
  - DoD: Pipeline passes on `main`; a PR that adds a `float` for money fails semgrep.
- **T0.18** Frontend web: Next.js 14 scaffold, Tailwind, shadcn/ui, generated API client, Zustand, TanStack Query. Minimal login/signup UI.
  - DoD: `make web` runs; user can log in through web UI.
- **T0.19** Frontend packages: shared `money/` (dinero.js wrapper), `types/` (generated), `ui/` (Button, Input, Dialog, Table, Toast).
  - DoD: UI package consumed by web app; typecheck passes.
- **T0.20** Docs: `docs/adr/0001-locked-stack.md`, `docs/adr/0002-audit-hash-chain.md`, `docs/adr/0003-multi-tenancy-rls.md`.
  - DoD: Each ADR follows the MADR template.

---

### **Phase 1 — Core Ledger (Weeks 3–6)**

**Objective.** A usable double-entry general ledger with CoA, manual journals, periods, multi-currency, and the two most foundational reports (TB, GL detail).

**Exit criteria.**
- [ ] A user can create accounts, post a balanced journal, see it in the GL, reverse it, close a period, and view a TB as of any date.
- [ ] Multi-currency JE stores functional and original amounts correctly; property tests cover FX math.
- [ ] All of §8.3–§8.5 rules enforced at all three layers (Pydantic, ORM, DB).
- [ ] Every action produces an audit event with before/after.

**Tasks.**

- **T1.1** Migration: `accounts`, `periods`, `fx_rates` tables per §8.3–§8.4 + §8.11 prereq.
- **T1.2** Repo + service for accounts: CRUD, archive, parent/child tree validation (no cycles).
  - DoD: Unit tests for tree integrity; integration for archive-blocked-when-used.
- **T1.3** Period management: generate periods for current + next fiscal year on tenant create; open/soft-close/hard-close/audited transitions.
  - DoD: State machine tests for all legal transitions; `hard_closed` blocks post.
- **T1.4** FX rates: table of (from, to, date, rate, source); daily job stub to pull rates (mock provider for now).
  - DoD: Lookup helper returns correct rate on a given date with fallback to last known.
- **T1.5** Migration: `journal_entries`, `journal_lines` per §8.5 with DB trigger enforcing balance.
- **T1.6** JE service: create draft, validate, post, void. Post emits domain event `journal.posted` consumed by audit.
  - DoD: Cannot post unbalanced; cannot edit posted; void creates mirror; all tested.
- **T1.7** JE API: `POST/GET/PATCH /v1/journals`, `POST /v1/journals/{id}/post`, `POST /v1/journals/{id}/void`. OpenAPI complete.
  - DoD: Contract tests pass. Idempotency keys honored.
- **T1.8** Accounts API + UI: CRUD page with tree view, inline edit, deactivate, CSV import (optional MVP).
  - DoD: Web `/accounts` page usable end-to-end.
- **T1.9** Journals UI: list + create page with line grid, balance indicator, post/void actions.
  - DoD: Web `/journals` page usable; keyboard flow for bookkeepers.
- **T1.10** Trial Balance report: as-of date, drill to account ledger; served from a lightweight query (no materialized view yet).
  - DoD: TB sums to zero for any as-of-date; regression test with a known fixture.
- **T1.11** General Ledger detail report: per account, with running balance, filters.
- **T1.12** Reports UI: `/reports/trial-balance`, `/reports/general-ledger` with filters + PDF/CSV export.
- **T1.13** Period close API + UI: soft-close → close checklist stubs → hard-close. Posting closing entries to Retained Earnings on year-end.
  - DoD: Running close creates the closing JE; reopen from soft only.
- **T1.14** FX revaluation job (skeleton): revalue open FX balances at period end; post FX gain/loss.
  - DoD: Manual trigger runs; produces JE; idempotent per period.
- **T1.15** AI read tools (bootstrap only, no chat yet): `get_account_balance`, `list_journal_entries`, `get_period_status`, `search_transactions`. Registered but unused.
  - DoD: Each tool has a JSON schema, handler, tests, and fixture-based assertions.

---

### **Phase 2 — Transactions, Reconciliation, Tax (Weeks 7–10)**

**Objective.** Daily accounting workflows: invoices, bills, payments, bank feeds, reconciliation, tax, core financial reports.

**Exit criteria.**
- [ ] A user can raise an invoice, send it, record a payment, reconcile the bank line, and see it flow into the P&L and BS.
- [ ] Same for a bill with approval workflow.
- [ ] Tax on a sale flows into the correct tax liability account and appears on the tax summary.
- [ ] Bank reconciliation matches manually and via proposed (rule-based) match; session closes cleanly.

**Tasks.**

- **T2.1** Migrations: `contacts`, `items`, `tax_codes`, `tax_rates` per §8.6–§8.7, §8.12.
- **T2.2** Contacts CRUD (API + UI) with merge and archive.
- **T2.3** Items CRUD (API + UI).
- **T2.4** Tax codes CRUD + country presets (US sales tax stubs, AU GST, UK VAT, HK no-tax, SG GST).
- **T2.5** Migrations + service: `invoices`, `invoice_lines`. Authorize action posts JE.
- **T2.6** Invoice API + UI: list, create, authorize, send (email via Mailhog in dev), void, credit note.
- **T2.7** Invoice PDF generation (background ARQ job using WeasyPrint or Playwright). Stored as `Document`.
- **T2.8** Migrations + service: `bills`, `bill_lines`, approval workflow (approver role required if amount > threshold).
- **T2.9** Bills API + UI with approval inbox.
- **T2.10** Migrations + service: `payments`, `payment_allocations`. Post JE; allocate to invoices/bills.
- **T2.11** Payments API + UI; partial payments supported.
- **T2.12** Bank accounts: `bank_accounts` + linking to GL account. Manual statement import (CSV/OFX).
- **T2.13** Bank feed provider adapter (`app/infra/banking/`): Plaid interface + mock implementation. Sync job fetches lines idempotently.
- **T2.14** Reconciliation engine: rule-based proposal (date ± 3 days, amount exact, contact name tokens).
- **T2.15** Reconciliation UI: Xero-style two-pane (statement line ↔ ledger) with match/split/create-new/exclude actions and session close.
- **T2.16** Expense claims: entity, submission, approval, linking to a bill or direct JE.
- **T2.17** Reports — P&L (accrual + cash basis toggle).
- **T2.18** Reports — Balance Sheet.
- **T2.19** Reports — AR aging, AP aging.
- **T2.20** Reports — Tax summary (BAS/GST/VAT-style).
- **T2.21** Materialized views for reports where queries > 200 ms on 100k JE synthetic dataset; incremental refresh on JE post.
- **T2.22** Seed script: demo tenant with 12 months of realistic data (for demos + perf tests).
- **T2.23** Cash Flow Statement (indirect method). *May slip to Phase 3 if time-boxed.*

---

### **Phase 3 — AI Assistant MVP (Weeks 11–13)**

**Objective.** Ship the Claude-powered assistant with read + draft + confirmed-mutation tools, citations, streaming, cost observability, and an eval harness.

**Exit criteria.**
- [ ] A user can chat with the assistant; it correctly answers "what's my cash balance?" by calling tools and citing IDs.
- [ ] Drafting a JE from natural language produces a valid proposal shown in the UI for confirmation.
- [ ] Executing a confirmed mutation posts the JE + generates an audit event with `actor_type='ai'` + conversation link.
- [ ] Receipt OCR produces a structured draft bill from a phone photo.
- [ ] Eval suite runs in CI; prompt changes that regress > 2 golden evals block merge.
- [ ] Cache hit rate > 70% on system+context tokens (measured over 100 test conversations).

**Tasks.**

- **T3.1** Anthropic SDK wiring (`anthropic` Python): config, per-tenant rate limiting via Redis token bucket, retry with exponential backoff.
- **T3.2** Conversation storage: `ai_conversations`, `ai_messages`, `ai_tool_calls` migrations. Token/cost accounting.
- **T3.3** System prompt v1 (`app/ai/prompts/system.md`): role, rules, citation requirement, never-invent clause. Versioned.
- **T3.4** Tenant-context builder: pulls COA summary, open period, recent activity window into a cacheable block.
- **T3.5** Tool schemas registry (`app/ai/tools/`): all T1.15 read tools + draft tools (`draft_journal_entry`, `draft_invoice`, `draft_bill`, `draft_reconciliation_match`) + mutation tools (`post_journal_entry`, `approve_bill`, `apply_reconciliation_match`).
- **T3.6** Orchestrator state machine: dispatches model calls, executes read/draft tools immediately, gates mutation tools behind `confirm_required`.
- **T3.7** Prompt caching: `cache_control: ephemeral` on system + tools + tenant-context blocks. Log cache metrics to Sentry/OTel.
- **T3.8** SSE endpoint `POST /v1/ai/conversations/{id}/messages` streaming deltas, tool events, confirmations.
- **T3.9** Response validator: post-hoc scan for unreferenced account codes/names and numeric values; attach `verify_flags` to response.
- **T3.10** Confirmation API: `POST /v1/ai/tool-calls/{id}/confirm` with the user's review; executes the tool server-side and emits audit event with `ai_conversation_id` metadata.
- **T3.11** Chat UI (web): conversation list, new message, streaming render, inline tool-call cards, confirmation modal with diff view.
- **T3.12** Receipt OCR: upload → Claude Vision (Sonnet 4.6) → structured output schema (vendor, date, total, tax, line items) → `documents.parsed` + draft bill suggestion.
- **T3.13** Anomaly detection v1: background job scans last 30 days of JEs for duplicates (same counterparty, amount, within 3 days), round-number anomalies, and Benford-violations on top accounts. Surfaced via notifications.
- **T3.14** NL reports: the assistant can produce a report snapshot; user confirms → snapshot stored immutably with hash (Phase 4 dependency).
- **T3.15** Eval harness (`ai-evals/`): YAML golden cases (prompt, expected tool sequence, expected citation set, forbidden hallucinations). `make ai-evals` runs; CI fails on regression.
- **T3.16** Cost dashboard: per-tenant daily/monthly token + USD; soft alerts to owners at 70% of cap; hard-stop at 100%.
- **T3.17** Admin UI: feature flag per tenant to enable/disable AI; per-user toggle for sensitive conversations.

---

### **Phase 4 — Audit Module (Weeks 14–15)**

**Objective.** Turn the audit log into a product: auditor workspaces, verification, sampling, evidence packages.

**Exit criteria.**
- [ ] An auditor can be invited with a time-scoped, read-only workspace.
- [ ] The hash chain verification dashboard is green for all tenants and alerts on break.
- [ ] Sampling tool returns reproducible samples (random + MUS + stratified) with seed.
- [ ] An evidence package (ZIP: PDFs + JSON + manifest + hash) can be generated for any date range and verified offline.

**Tasks.**

- **T4.1** Audit verification worker: daily walk of each tenant's hash chain; write results to `audit_chain_verifications`. Alert on break (Sentry + email to owner).
- **T4.2** Audit timeline API + UI: filter by date, actor, action, entity. Pagination. Search.
- **T4.3** Hash-chain verification dashboard (auditor + admin view): green/red per tenant, last verified, chain length, any prior break history.
- **T4.4** Auditor role wiring: scoped permissions (read-all business data, read audit, create evidence packages, *no* write). External auditor invite flow (email, time-boxed, optional IP allowlist).
- **T4.5** Sampling tool API: `POST /v1/audit/samples` with params `{population_query, method: random|mus|stratified, size, seed}`. Reproducible.
- **T4.6** JE testing reports: cutoff (entries near period boundary), weekend/holiday posts, round numbers, entries by non-accountants, top-N largest, reversed same-day entries.
- **T4.7** Evidence package builder: background job produces ZIP with: PDFs of journals in scope, CSV of lines, OCR originals, audit events, hash manifest, README with verification instructions.
- **T4.8** Report snapshots: any report can be "snapshotted" — stored immutably with sha256, referenceable from audit.
- **T4.9** Audit request workflow: intake (title, scope, requester), respond (attach evidence package + comments), close (sign-off).
- **T4.10** AI audit Q&A (`ai-09`): auditor-mode assistant that only runs read tools + sampling tools; outputs include hash-chain proof references.
- **T4.11** GDPR export: per-user data export; rate-limited; logged as audit event.

---

### **Phase 5 — Mobile App (Weeks 16–18)**

**Objective.** Ship iOS + Android apps for capture, approvals, and read access, with offline-first sync.

**Exit criteria.**
- [ ] A user can log in with biometric, capture a receipt offline, then sync cleanly online with the draft linked to a new expense claim.
- [ ] Approvals inbox on mobile lets approvers approve/reject bills with a visible audit trail.
- [ ] Conflict rate < 0.5% on synthetic 100-device test.
- [ ] Deep link from push notification opens the relevant entity.

**Tasks.**

- **T5.1** Expo app scaffold; Expo Router layout with tab navigation; theme + design tokens from `packages/ui`.
- **T5.2** Auth flow: email/password login, biometric prompt, PIN fallback, secure token storage.
- **T5.3** Local `op-sqlite` DB schema + migrations; encryption with device-bound key.
- **T5.4** Sync engine: pull-since-cursor, push batch, conflict detection + resolution rules from §13.
- **T5.5** Backend sync endpoints `/v1/sync/pull`, `/v1/sync/push` with Lamport cursors and idempotent ops.
- **T5.6** Receipt capture screen: camera, crop, compression, queue upload.
- **T5.7** Expense claim: create from receipt, select category (AI-suggested via Haiku), submit for approval.
- **T5.8** Approvals inbox: list of pending items by type, detail view, approve/reject with reason.
- **T5.9** Dashboard widgets: cash position, AR aging top 5, AP due this week, AI-flagged anomalies.
- **T5.10** Recent transactions + search + detail view.
- **T5.11** Push notifications via Expo: tokens registered per device, FCM + APNs delivery, deep links.
- **T5.12** AI chat (mobile): reuse web chat component adapted for mobile; voice-to-text via native speech APIs.
- **T5.13** Detox E2E: login, offline capture, sync, approve, dashboard.
- **T5.14** Store submission artifacts: icons, screenshots, privacy policy link, App Store / Play Store listings.

---

### **Phase 6 — Advanced ERP & Integrations (Weeks 19–24)**

**Objective.** Broaden into ERP territory and ship the integrations that unlock real customers.

**Tasks (selected; scope negotiated by the user before start).**

- **T6.1** SSO: OIDC + SAML (work/Okta/Azure AD).
- **T6.2** Billing & subscriptions (Stripe) with per-tenant plans and usage-based AI overage.
- **T6.3** Real Plaid / TrueLayer integration (replaces mock).
- **T6.4** Stripe payments in: invoice "pay now" link; webhook reconciles payment + creates JE.
- **T6.5** Payroll integration: Gusto (US), Deel (global) — pulls pay runs into AP bills or direct JE.
- **T6.6** Shopify / WooCommerce: daily sales summaries → draft JEs.
- **T6.7** Inventory (light): tracked items, perpetual inventory, COGS on sale, stocktake adjustments.
- **T6.8** Projects / jobs: cost tracking dimension on lines; project P&L report.
- **T6.9** Intercompany & consolidation (basic): parent/subsidiary tenants, consolidation report.
- **T6.10** Custom report builder (WYSIWYG with GL filters + pivots).
- **T6.11** Public REST API polish + API keys + OAuth 2 for third parties + rate limits.
- **T6.12** Webhooks (outbound): event types, signing secret, retry queue, replay UI.
- **T6.13** Admin backoffice (for Aegis internal): tenant list, suspend, switch-to (impersonate with audit), metrics.
- **T6.14** Data residency: region selection on signup; geo-routed writes/reads.

---

### **Phase 7 — Marketplace, Advanced AI, Polish (Post-V1)**

- OAuth app directory and developer portal.
- AI month-end close copilot (orchestrates the full close checklist).
- AI month-over-month variance explanations auto-posted to each report.
- Segregation-of-duties analyzer + recommendations.
- Scheduled report emails + Slack/Teams digests.
- Multi-entity consolidation (advanced: elimination entries, intercompany FX).
- Budgeting & forecasting + AI-generated budget drafts.
- Industry templates (agencies, e-commerce, restaurants).

---

## 10. Execution tracker

> **Agent: keep this up to date.** Change the status column in the same PR as the task's implementation.

Legend: ⬜ not started · 🟨 in progress · ✅ done · 🚫 blocked

### Phase 0
| ID | Task | Status | PR |
|----|------|--------|----|
| T0.1 | Monorepo scaffolding + Makefile | ✅ | init |
| T0.2 | Backend pyproject.toml + FastAPI skeleton + smoke test | ✅ | init |
| T0.3 | Docker Compose dev services + .env.example | ✅ | init |
| T0.4 | Alembic env + base migration (0001) | ✅ | init |
| T0.5 | Config (Pydantic Settings), structlog, Sentry wiring | ✅ | init |
| T0.6 | Money module + unit tests + property tests | ✅ | init |
| T0.7 | Multi-tenancy context var + RLS session helper | ✅ | init |
| T0.8 | Security utils (Argon2id, JWT, tokens) + unit tests | ✅ | init |
| T0.9 | MFA (TOTP + WebAuthn) | ✅ | phase0-cont |
| T0.10 | RBAC permissions registry + matrix unit tests | ✅ | init |
| T0.11 | Audit log write-side (emitter + hash chain) | ✅ | init |
| T0.12 | Audit append-only Postgres trigger (in 0001 migration) | ✅ | init |
| T0.13 | Tenant onboarding + CoA templates (US, AU) | ✅ | phase0-cont |
| T0.14 | User invites (Invite model in 0001, service in phase 1 auth) | ✅ | phase0-cont |
| T0.15 | Feature flags service (is_enabled, set_global, set_tenant) | ✅ | phase0-cont |
| T0.16 | OTel auto-instrumentation (FastAPI + SQLAlchemy) | ✅ | phase0-cont |
| T0.17 | CI pipeline (GitHub Actions) | ✅ | init |
| T0.18 | Next.js 14 web scaffold + login UI + middleware + providers | ✅ | phase0-cont |
| T0.19 | Frontend packages: @aegis/ui @aegis/types @aegis/money @aegis/api-client | ✅ | phase0-cont |
| T0.20 | ADRs 0001–0003 | ✅ | init |

### Phase 1
| ID | Task | Status | PR |
|----|------|--------|----|
| T1.1 | Accounts/periods/fx migrations | ✅ | |
| T1.2 | Accounts service | ✅ | |
| T1.3 | Period management | ✅ | |
| T1.4 | FX rates | ✅ | |
| T1.5 | JE migrations + trigger | ✅ | |
| T1.6 | JE service | ✅ | |
| T1.7 | JE API | ✅ | |
| T1.8 | Accounts UI | ⬜ | |
| T1.9 | Journals UI | ⬜ | |
| T1.10 | Trial Balance report | ✅ | |
| T1.11 | General Ledger report | ✅ | |
| T1.12 | Reports UI | ⬜ | |
| T1.13 | Period close | 🟨 | API done, UI pending |
| T1.14 | FX revaluation | 🟨 | skeleton only |
| T1.15 | AI read tools (bootstrap) | ⬜ | |

### Phase 2
| ID | Task | Status | PR |
|----|------|--------|----|
| T2.1 | Contacts/items/tax migrations | ⬜ | |
| T2.2 | Contacts CRUD | ⬜ | |
| T2.3 | Items CRUD | ⬜ | |
| T2.4 | Tax codes + country presets | ⬜ | |
| T2.5 | Invoice migrations + service | ⬜ | |
| T2.6 | Invoice API + UI | ⬜ | |
| T2.7 | Invoice PDF | ⬜ | |
| T2.8 | Bill migrations + approval | ⬜ | |
| T2.9 | Bills API + UI | ⬜ | |
| T2.10 | Payments + allocations | ⬜ | |
| T2.11 | Payments API + UI | ⬜ | |
| T2.12 | Bank accounts + CSV import | ⬜ | |
| T2.13 | Bank feed adapter + mock | ⬜ | |
| T2.14 | Reconciliation engine | ⬜ | |
| T2.15 | Reconciliation UI | ⬜ | |
| T2.16 | Expense claims | ⬜ | |
| T2.17 | P&L report | ⬜ | |
| T2.18 | Balance Sheet | ⬜ | |
| T2.19 | Aging reports | ⬜ | |
| T2.20 | Tax summary | ⬜ | |
| T2.21 | Materialized views | ⬜ | |
| T2.22 | Demo seed | ⬜ | |
| T2.23 | Cash Flow Statement | ⬜ | |

### Phase 3
| ID | Task | Status | PR |
|----|------|--------|----|
| T3.1 | Anthropic SDK wiring | ⬜ | |
| T3.2 | Conversation storage | ⬜ | |
| T3.3 | System prompt v1 | ⬜ | |
| T3.4 | Tenant-context builder | ⬜ | |
| T3.5 | Tool schemas registry | ⬜ | |
| T3.6 | Orchestrator state machine | ⬜ | |
| T3.7 | Prompt caching | ⬜ | |
| T3.8 | SSE streaming endpoint | ⬜ | |
| T3.9 | Response validator | ⬜ | |
| T3.10 | Mutation confirmation API | ⬜ | |
| T3.11 | Chat UI (web) | ⬜ | |
| T3.12 | Receipt OCR | ⬜ | |
| T3.13 | Anomaly detection v1 | ⬜ | |
| T3.14 | NL reports + snapshot | ⬜ | |
| T3.15 | Eval harness | ⬜ | |
| T3.16 | Cost dashboard | ⬜ | |
| T3.17 | Admin AI toggles | ⬜ | |

### Phase 4
| ID | Task | Status | PR |
|----|------|--------|----|
| T4.1 | Chain verification worker | ⬜ | |
| T4.2 | Audit timeline API+UI | ⬜ | |
| T4.3 | Verification dashboard | ⬜ | |
| T4.4 | Auditor role + invites | ⬜ | |
| T4.5 | Sampling tool | ⬜ | |
| T4.6 | JE testing reports | ⬜ | |
| T4.7 | Evidence packages | ⬜ | |
| T4.8 | Report snapshots | ⬜ | |
| T4.9 | Audit request workflow | ⬜ | |
| T4.10 | AI auditor mode | ⬜ | |
| T4.11 | GDPR export | ⬜ | |

### Phase 5
| ID | Task | Status | PR |
|----|------|--------|----|
| T5.1 | Expo scaffold + nav | ⬜ | |
| T5.2 | Auth + biometric | ⬜ | |
| T5.3 | Encrypted local DB | ⬜ | |
| T5.4 | Sync engine (client) | ⬜ | |
| T5.5 | Sync endpoints (server) | ⬜ | |
| T5.6 | Receipt capture | ⬜ | |
| T5.7 | Expense claim flow | ⬜ | |
| T5.8 | Approvals inbox | ⬜ | |
| T5.9 | Dashboard widgets | ⬜ | |
| T5.10 | Transactions + search | ⬜ | |
| T5.11 | Push notifications | ⬜ | |
| T5.12 | Mobile AI chat | ⬜ | |
| T5.13 | Detox E2E | ⬜ | |
| T5.14 | Store submission assets | ⬜ | |

---

## 11. Blockers & decisions log

> Add an entry whenever you hit a decision the product owner must make, or a blocker that requires a human.

| Date | Raised by | Task | What's blocked | Options | Decision | Resolver |
|------|-----------|------|----------------|---------|----------|----------|
| _add entries below this line_ | | | | | | |

---

## 12. Parking lot

Ideas that surface during execution but don't belong in the current phase. Triaged at the end of each phase.

- Consolidation & elimination entries (ACC-15) — when V1 ships with 2+ big customers asking for it.
- AI-generated budgets — depends on reliable forecasting and multi-scenario modeling.
- "Open in Excel" live export (requires ETag + signed URL, nice-to-have).

---

## 13. Risks & mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| AI hallucinates account names / amounts | H | H | Tool-only grounding, citation validator, eval gating (§11.4) |
| Hash chain breaks (silent data corruption) | L | Critical | Append-only trigger, daily verification worker, alerts, quarterly restore drill |
| Cross-tenant data leak | M | Critical | RLS + ORM guard + per-request context + explicit leak tests |
| Money precision drift (float creep) | M | Critical | Semgrep rule, property tests, Money type mandatory |
| Bank feed provider outage | M | M | Multi-provider adapter, manual CSV import fallback, last-known cache |
| AI cost runaway | M | M | Per-tenant token bucket + hard caps + Sentry alerts |
| Mobile sync corruption | L | H | Lamport clocks + idempotent push + conflict log + client-side invariants |
| Vendor lock-in on Anthropic | L | M | Orchestrator talks to a small internal interface; swap is < 2 weeks |
| Pen-test finding at GA | M | H | Run internal pen test mid-Phase 6 |

---

## 14. Open questions (for the product owner)

1. **Project name.** "Aegis" is a working title — confirm or choose a new one.
2. **Launch geographies.** US + AU at GA? Add UK/SG/HK at V1.5?
3. **Pricing model.** Seat-based + AI usage? Or bundled? Affects Stripe schema.
4. **Tax engine.** Build in-house for US sales tax, or integrate Stripe Tax / Avalara?
5. **Payroll scope.** Integration-only (Phase 6), or ever build native?
6. **Mobile parity.** Is mobile read-only OK for Phase 5, or must include invoicing?
7. **Custom branding.** White-label for accounting firms at GA or V1.5?
8. **Data residency.** Required at launch, or can start US-only and add regions as deals come?
9. **Compliance roadmap.** SOC2 Type I at 6 months, Type II at 12? ISO 27001 timing?
10. **Auditor-workspace billing.** Free for external auditors, or seat?

Answers here flip scope for Phase 6 onwards.

---

## 15. Glossary

See `CLAUDE.md §19`. Plus:

| Term | Meaning |
|------|---------|
| **MUS** | Monetary Unit Sampling — audit sampling weighted by value |
| **ADR** | Architecture Decision Record |
| **JTBD** | Jobs To Be Done |
| **MVP** | Minimum Viable Product (our MVP = Phase 0–2 + a sliver of 3) |
| **MADR** | Markdown Architectural Decision Records template |
| **RLS** | Row-Level Security |
| **SSE** | Server-Sent Events |

---

## 16. Change log

| Version | Date | Change |
|---------|------|--------|
| 1.0 | 2026-04-14 | Initial PRP authored. |
