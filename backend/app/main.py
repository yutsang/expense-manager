from __future__ import annotations

import time

import sentry_sdk
import structlog
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.logging import configure_logging

settings = get_settings()
configure_logging(debug=settings.debug)
log = structlog.get_logger(__name__)

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
    allow_origins=["http://localhost:3000", "http://localhost:8081"],
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


# ─── Routers (registered as phases implement them) ───────────────────────────
# from app.api.v1 import auth, tenants, users  # noqa: E402  (uncomment per phase)


@app.get("/healthz", tags=["meta"], summary="Health check")
async def healthz() -> dict[str, str]:
    return {"status": "ok", "version": app.version}


@app.get("/", include_in_schema=False)
async def root() -> dict[str, str]:
    return {"message": "Aegis ERP API — see /docs"}
