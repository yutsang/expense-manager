"""Ops API — authenticated cron trigger endpoints.

Cloud Run doesn't host a persistent ARQ worker, so Cloud Scheduler invokes
these endpoints on schedule to run the jobs defined in
``app/workers/sanctions_refresh.py`` etc. Jobs run *synchronously* inside
the request — Cloud Run keeps CPU allocated for the request lifetime, but
not for FastAPI background tasks that outlive the response, so a long
sanctions refresh dispatched as a background task gets silently killed
mid-stream (observed 2026-04-25). Cloud Scheduler retries up to 30 min, and
we have ``timeoutSeconds=3600`` on the service, which is plenty.

Authentication: shared secret via ``X-Cron-Secret`` header, configured as
``CRON_SECRET`` env var on the Cloud Run service.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Annotated, Any

from fastapi import APIRouter, Header, HTTPException, status

from app.core.config import get_settings
from app.core.logging import get_logger
from app.workers.fx_rate_fetcher import fetch_ecb_rates
from app.workers.sanctions_refresh import refresh_sanctions_lists
from app.workers.verify_audit_chain import verify_all_tenants

router = APIRouter(prefix="/_ops", tags=["ops"], include_in_schema=False)
log = get_logger(__name__)

_JOBS: dict[str, Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]] = {
    "sanctions-refresh": refresh_sanctions_lists,
    "fx-rates": fetch_ecb_rates,
    "verify-audit": verify_all_tenants,
}


def _check_secret(x_cron_secret: str | None) -> None:
    configured = get_settings().cron_secret
    if not configured or x_cron_secret != configured:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)


@router.post("/cron/{job_name}", status_code=status.HTTP_200_OK)
async def run_cron(
    job_name: str,
    x_cron_secret: Annotated[str | None, Header(alias="X-Cron-Secret")] = None,
) -> dict[str, Any]:
    """Run a named cron job synchronously and return its result. Long-running
    by design — sanctions-refresh can take 5–10 minutes on the OpenSanctions
    Default feed.
    """
    _check_secret(x_cron_secret)
    fn = _JOBS.get(job_name)
    if fn is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown job: {job_name}",
        )

    log.info("ops.cron_started", job=job_name)
    try:
        result = await fn({})
        log.info("ops.cron_completed", job=job_name, result=result)
        return {"status": "completed", "job": job_name, "result": result}
    except Exception as exc:  # noqa: BLE001
        log.error("ops.cron_failed", job=job_name, error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Job {job_name} failed: {exc}",
        ) from exc
