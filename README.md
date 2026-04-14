# Aegis ERP

> **Status:** Pre-alpha. Planning complete; implementation kicking off.
> **Working title** — rename at will.

An AI-native, audit-first ERP and accounting platform in the Xero/QuickBooks Online class, with an embedded Claude assistant, a dedicated auditor workspace, and an offline-first mobile companion.

## Why this exists

Small and mid-size businesses outgrow spreadsheets but hit three walls with existing tools:

1. **AI bolt-ons** are toys — they generate nice prose but invent account names.
2. **Audit requests** still mean shipping zip files of JPGs and spreadsheets.
3. **Mobile apps** are read-mostly shells that forget they're offline.

Aegis fixes all three as first-class concerns.

## What's in this repo

| Path | What |
|------|------|
| [`CLAUDE.md`](./CLAUDE.md) | **How** we build — conventions, rails, domain rules. Binding for any agent working here. Start here. |
| [`docs/PRP.md`](./docs/PRP.md) | **What** we build — product requirements, architecture, phased plan with atomic tasks an agent can execute. |
| `docs/adr/` | Architecture decision records. |
| `docs/domain/` | Accounting/audit domain primers (populated during Phase 0). |
| `backend/`, `frontend/`, `infra/`, `scripts/` | Scaffolded in Phase 0, task **T0.1**. |

## For humans

- Read `CLAUDE.md` § 1–4 for the 10-minute orientation.
- Read `docs/PRP.md` § 1–6 for scope and feature map.
- Execution phases are in `docs/PRP.md` § 9, with a live tracker in § 10.

## For coding agents

You're expected to work through `docs/PRP.md` § 9 phase-by-phase, honoring `CLAUDE.md` in every PR. Follow the "How an agent should execute this plan" preamble in § 0 of the PRP.

## License

MIT — see [`LICENSE`](./LICENSE).
