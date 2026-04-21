"""Ops API — authenticated cron trigger endpoints.

Cloud Run doesn't host a persistent ARQ worker, so Cloud Scheduler invokes
these endpoints on schedule to run the jobs defined in
``app/workers/settings.py``. The underlying worker functions create their own
``AsyncSessionLocal()`` sessions and are safe to run in a ``BackgroundTasks``
dispatch after the HTTP response has returned.

Authentication: shared secret via ``X-Cron-Secret`` header, configured as
``CRON_SECRET`` env var on the Cloud Run service.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, status

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


@router.post("/cron/{job_name}", status_code=status.HTTP_202_ACCEPTED)
async def run_cron(
    job_name: str,
    background_tasks: BackgroundTasks,
    x_cron_secret: Annotated[str | None, Header(alias="X-Cron-Secret")] = None,
) -> dict[str, str]:
    """Run a named cron job in the background. Returns 202 immediately."""
    _check_secret(x_cron_secret)
    fn = _JOBS.get(job_name)
    if fn is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown job: {job_name}",
        )

    async def _runner() -> None:
        try:
            result = await fn({})
            log.info("ops.cron_completed", job=job_name, result=result)
        except Exception as exc:  # noqa: BLE001
            log.error("ops.cron_failed", job=job_name, error=str(exc))

    background_tasks.add_task(_runner)
    return {"status": "queued", "job": job_name}
