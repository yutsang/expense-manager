.PHONY: help bootstrap up down dev api web mobile \
        migrate migrate-down migration seed db-shell \
        test test-slow lint fix typecheck coverage \
        ai-evals ai-evals-diff openapi client-gen

BACKEND_DIR := backend
FRONTEND_DIR := frontend

# ─── Help ────────────────────────────────────────────────────────────────────

help:
	@echo ""
	@echo "Aegis ERP — available targets"
	@echo ""
	@echo "  Setup"
	@echo "    bootstrap       Install all deps + pre-commit hooks"
	@echo "    up              Start local Docker services (postgres, redis, minio, mailhog)"
	@echo "    down            Stop local Docker services"
	@echo ""
	@echo "  Dev"
	@echo "    dev             Run api + web + mobile in parallel (requires overmind or tmux)"
	@echo "    api             Run FastAPI backend only"
	@echo "    web             Run Next.js frontend only"
	@echo "    mobile          Run Expo mobile only"
	@echo ""
	@echo "  Database"
	@echo "    migrate         Apply all pending Alembic migrations"
	@echo "    migrate-down    Roll back n migrations  (n=1)"
	@echo "    migration       Generate new Alembic revision  (m='desc')"
	@echo "    seed            Reset DB and load demo data"
	@echo "    db-shell        Open psql shell against local DB"
	@echo ""
	@echo "  Quality"
	@echo "    test            Fast tests (unit + property, < 30 s)"
	@echo "    test-slow       All tests including integration + e2e"
	@echo "    lint            Run all linters (ruff, mypy, biome, tsc)"
	@echo "    fix             Auto-fix lint issues"
	@echo "    typecheck       mypy + tsc --noEmit"
	@echo "    coverage        Generate coverage report"
	@echo ""
	@echo "  AI"
	@echo "    ai-evals        Run AI evaluation suite"
	@echo "    ai-evals-diff   Compare current evals to baseline"
	@echo ""
	@echo "  Release"
	@echo "    openapi         Export OpenAPI spec to docs/"
	@echo "    client-gen      Regenerate TS API client from OpenAPI"
	@echo ""

# ─── Setup ───────────────────────────────────────────────────────────────────

bootstrap:
	@echo "→ Installing Python deps..."
	cd $(BACKEND_DIR) && pip install -e ".[dev]"
	@echo "→ Installing frontend deps..."
	cd $(FRONTEND_DIR) && pnpm install
	@echo "→ Installing pre-commit hooks..."
	pre-commit install
	@echo "✓ Bootstrap complete"

up:
	docker compose -f infra/docker/compose.dev.yml up -d
	@echo "✓ Services up — Postgres :5432, Redis :6379, MinIO :9000, Mailhog :8025"

down:
	docker compose -f infra/docker/compose.dev.yml down

# ─── Dev ─────────────────────────────────────────────────────────────────────

dev:
	@command -v overmind >/dev/null 2>&1 && overmind start -f Procfile.dev || \
	  (echo "overmind not found; run 'make api', 'make web', 'make mobile' in separate terminals")

api:
	cd $(BACKEND_DIR) && uvicorn app.main:app --reload --port 8000

web:
	cd $(FRONTEND_DIR)/apps/web && pnpm dev

mobile:
	cd $(FRONTEND_DIR)/apps/mobile && pnpm expo start

# ─── Database ────────────────────────────────────────────────────────────────

migrate:
	cd $(BACKEND_DIR) && alembic upgrade head

migrate-down:
	cd $(BACKEND_DIR) && alembic downgrade -$(or $(n),1)

migration:
	@test -n "$(m)" || (echo "Usage: make migration m='ledger: add period status'" && exit 1)
	cd $(BACKEND_DIR) && alembic revision --autogenerate -m "$(m)"

seed:
	cd $(BACKEND_DIR) && python -m scripts.seed

db-shell:
	@docker compose -f infra/docker/compose.dev.yml exec postgres \
	  psql -U aegis -d aegis_dev

# ─── Quality ─────────────────────────────────────────────────────────────────

test:
	cd $(BACKEND_DIR) && pytest tests/unit tests/property -q --tb=short

test-slow:
	cd $(BACKEND_DIR) && pytest tests/ -q --tb=short
	cd $(FRONTEND_DIR) && pnpm test

lint:
	cd $(BACKEND_DIR) && ruff check . && mypy .
	cd $(FRONTEND_DIR) && pnpm biome check .

fix:
	cd $(BACKEND_DIR) && ruff check --fix . && black .
	cd $(FRONTEND_DIR) && pnpm biome check --write .

typecheck:
	cd $(BACKEND_DIR) && mypy .
	cd $(FRONTEND_DIR) && pnpm tsc --noEmit

coverage:
	cd $(BACKEND_DIR) && pytest --cov=app --cov-report=html tests/
	@echo "→ Open backend/htmlcov/index.html"

# ─── AI ──────────────────────────────────────────────────────────────────────

ai-evals:
	cd $(BACKEND_DIR) && python -m ai_evals.run

ai-evals-diff:
	cd $(BACKEND_DIR) && python -m ai_evals.diff

# ─── Release ─────────────────────────────────────────────────────────────────

openapi:
	cd $(BACKEND_DIR) && python -c \
	  "import json; from app.main import app; \
	   open('../docs/openapi.json','w').write(json.dumps(app.openapi(),indent=2))"
	@echo "✓ Exported to docs/openapi.json"

client-gen:
	cd $(FRONTEND_DIR) && pnpm openapi-ts \
	  --input ../docs/openapi.json \
	  --output packages/api-client/src/generated \
	  --client fetch
	@echo "✓ Client regenerated"
