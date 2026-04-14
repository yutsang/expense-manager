# ADR 0001 — Locked Technology Stack

**Date:** 2026-04-14
**Status:** Accepted
**Deciders:** Product owner, lead architect

---

## Context

Before writing a line of product code we need to lock the technology choices that will be hard to change later. Premature pivots mid-build are expensive.

## Decision

The stack described in `CLAUDE.md §4` is the locked default:

- **Backend:** Python 3.12 + FastAPI + SQLAlchemy 2.0 (async) + Alembic + PostgreSQL 16
- **AI:** Anthropic SDK — Claude Sonnet 4.6 (default), Opus 4.6 (analysis), Haiku 4.5 (classifiers)
- **Frontend Web:** Next.js 14 (App Router) + TypeScript 5 + Tailwind + shadcn/ui
- **Frontend Mobile:** Expo SDK 51 (React Native)
- **Queue / Cache:** Redis 7 + ARQ
- **Object Store:** S3-compatible (MinIO dev, R2/S3 prod)
- **Auth:** Custom JWT (HS256) + Argon2id passwords

## Consequences

- Changing any of these requires a new ADR and product owner approval.
- Agents must not introduce alternative ORMs, frameworks, or AI providers without this process.
- The AI vendor choice (Anthropic) is abstracted behind `app/ai/orchestrator.py` — a swap is possible in < 2 weeks if ever needed.
