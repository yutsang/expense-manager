"""Aggregate ARQ WorkerSettings.

Run locally with::

    arq app.workers.settings.WorkerSettings

In the Cloud Run deployment we don't host a persistent ARQ worker; the same
functions are invoked via Cloud Scheduler → ``POST /v1/_ops/cron/{job_name}``
(see ``app/api/v1/ops.py``). This module is the single source of truth for
cron schedules regardless of which execution path is used.
"""

from __future__ import annotations

from arq.connections import RedisSettings
from arq.cron import cron

from app.core.config import get_settings
from app.workers.fx_rate_fetcher import fetch_ecb_rates
from app.workers.sanctions_refresh import refresh_sanctions_lists
from app.workers.verify_audit_chain import verify_all_tenants

_settings = get_settings()


class WorkerSettings:
    redis_settings = RedisSettings.from_dsn(str(_settings.redis_url))
    functions = [refresh_sanctions_lists, fetch_ecb_rates, verify_all_tenants]
    cron_jobs = [
        cron(refresh_sanctions_lists, hour=1, minute=0),
        cron(fetch_ecb_rates, hour=16, minute=30),
        cron(verify_all_tenants, hour=2, minute=0),
    ]
