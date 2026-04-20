from __future__ import annotations

import time

import sentry_sdk
import structlog
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.core.telemetry import configure_telemetry

settings = get_settings()
configure_logging(debug=settings.debug)
log = structlog.get_logger(__name__)

# OpenTelemetry (no-op if endpoint is empty in dev)
configure_telemetry(
    app_name=settings.app_name,
    environment=settings.environment,
    otlp_endpoint=settings.otel_exporter_otlp_endpoint,
)

# Sentry (no-op if dsn is empty)
if settings.sentry_dsn:
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.environment,
        traces_sample_rate=0.1,
        profiles_sample_rate=0.1,
    )

app = FastAPI(
    title="Aegis ERP API",
    version="0.1.0",
    docs_url="/docs" if not settings.is_production else None,
    redoc_url="/redoc" if not settings.is_production else None,
    openapi_url="/openapi.json" if not settings.is_production else None,
)

# CORS — tighten in prod via env
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:8081",
        "https://aegis-erp-web.vercel.app",
        *([settings.frontend_url] if getattr(settings, "frontend_url", None) else []),
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_context_middleware(request: Request, call_next: object) -> Response:
    """Inject request_id and structured log context for every request."""
    import uuid

    request_id = str(uuid.uuid4())
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(
        request_id=request_id,
        method=request.method,
        path=request.url.path,
    )
    start = time.perf_counter()
    response: Response = await call_next(request)  # type: ignore[operator]
    elapsed_ms = round((time.perf_counter() - start) * 1000, 1)
    log.info("request", status=response.status_code, elapsed_ms=elapsed_ms)
    response.headers["X-Request-Id"] = request_id
    return response


# ─── Routers ────────────────────────────────────────────────────────────────
from app.api.v1 import (  # noqa: E402
    accounts,
    accruals,
    ai,
    approval_rules,
    attachments,
    audit,
    auth,
    bank_feeds,
    bank_reconciliation,
    bills,
    budgets,
    consolidation,
    contacts,
    expense_claims,
    fixed_assets,
    fx,
    invoice_portal,
    invoice_templates,
    invoices,
    items,
    journals,
    kyc,
    onboarding,
    payments,
    payroll,
    periods,
    projects,
    purchase_orders,
    receipts,
    reports,
    sales_documents,
    sanctions,
    search,
    sync,
    tenant_settings,
    users,
)

_API_PREFIX = "/v1"
app.include_router(accounts.router, prefix=_API_PREFIX)
app.include_router(tenant_settings.router, prefix=_API_PREFIX)
app.include_router(periods.router, prefix=_API_PREFIX)
app.include_router(fx.router, prefix=_API_PREFIX)
app.include_router(journals.router, prefix=_API_PREFIX)
app.include_router(reports.router, prefix=_API_PREFIX)
app.include_router(contacts.router, prefix=_API_PREFIX)
app.include_router(items.router, prefix=_API_PREFIX)
app.include_router(invoices.router, prefix=_API_PREFIX)
app.include_router(bills.router, prefix=_API_PREFIX)
app.include_router(auth.router, prefix=_API_PREFIX)
app.include_router(payments.router, prefix=_API_PREFIX)
app.include_router(bank_feeds.router, prefix=_API_PREFIX)
app.include_router(bank_reconciliation.router, prefix=_API_PREFIX)
app.include_router(expense_claims.router, prefix=_API_PREFIX)
app.include_router(ai.router, prefix=_API_PREFIX)
app.include_router(audit.router, prefix=_API_PREFIX)
app.include_router(sync.router, prefix=_API_PREFIX)
app.include_router(kyc.router, prefix=_API_PREFIX)
app.include_router(sanctions.router, prefix=_API_PREFIX)
app.include_router(receipts.router, prefix=_API_PREFIX)
app.include_router(sales_documents.router, prefix=_API_PREFIX)
app.include_router(purchase_orders.router, prefix=_API_PREFIX)
app.include_router(attachments.router, prefix=_API_PREFIX)
app.include_router(onboarding.router, prefix=_API_PREFIX)
app.include_router(invoice_portal.router, prefix=_API_PREFIX)
app.include_router(invoice_portal.public_router, prefix=_API_PREFIX)
app.include_router(search.router, prefix=_API_PREFIX)
app.include_router(accruals.router, prefix=_API_PREFIX)
app.include_router(fixed_assets.router, prefix=_API_PREFIX)
app.include_router(payroll.router, prefix=_API_PREFIX)
app.include_router(budgets.router, prefix=_API_PREFIX)
app.include_router(invoice_templates.router, prefix=_API_PREFIX)
app.include_router(users.router, prefix=_API_PREFIX)
app.include_router(consolidation.router, prefix=_API_PREFIX)
app.include_router(approval_rules.router, prefix=_API_PREFIX)
app.include_router(projects.router, prefix=_API_PREFIX)
app.include_router(projects.time_entries_router, prefix=_API_PREFIX)
app.include_router(projects.billing_rates_router, prefix=_API_PREFIX)


@app.get("/health", tags=["meta"], summary="Health check")
async def health() -> dict[str, str]:
    return {"status": "ok", "version": app.version}


@app.get("/", include_in_schema=False)
async def root() -> dict[str, str]:
    return {"message": "Aegis ERP API — see /docs"}
