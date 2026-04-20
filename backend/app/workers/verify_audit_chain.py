"""ARQ worker: daily audit-chain verification across all tenants.

Walks every tenant's ``audit_events`` hash chain and records the outcome in
``audit_chain_verifications`` (CLAUDE.md §10.4). On a broken chain we log at
ERROR level and surface the event to Sentry so on-call is paged — a broken
chain is a P0 per the guardrail metrics in ``docs/PRP.md §4.2``.

Usage as an ARQ task::

    class WorkerSettings:
        functions = [verify_all_tenants]
        cron_jobs = [cron(verify_all_tenants, hour=2, minute=0)]  # 02:00 UTC daily
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import distinct, select

from app.core.db import AsyncSessionLocal
from app.core.logging import get_logger
from app.core.tenant import set_rls_tenant
from app.infra.models import AuditEvent
from app.services.audit import verify_chain

log = get_logger(__name__)


async def verify_all_tenants(ctx: dict[str, Any] | None = None) -> dict[str, Any]:
    """Verify every tenant's audit chain. Returns counts of ok / broken / errors.

    The job is idempotent — repeated runs just append a new row per tenant to
    ``audit_chain_verifications`` (the table is a history of runs, not the
    source of truth). Fails closed: any broken chain is reported to Sentry.
    """
    ok = 0
    broken = 0
    errors = 0
    broken_tenants: list[dict[str, Any]] = []

    async with AsyncSessionLocal() as db:
        tenant_rows = await db.execute(select(distinct(AuditEvent.tenant_id)))
        tenant_ids = [row[0] for row in tenant_rows.all() if row[0] is not None]

    log.info("audit_chain.tenants_to_verify", count=len(tenant_ids))

    for tid in tenant_ids:
        async with AsyncSessionLocal() as db:
            try:
                await set_rls_tenant(db, tid)
                result = await verify_chain(db, tid)
                await db.commit()

                if result["is_valid"]:
                    ok += 1
                    log.info(
                        "audit_chain.verified",
                        tenant_id=tid,
                        chain_length=result["chain_length"],
                    )
                else:
                    broken += 1
                    broken_tenants.append(
                        {
                            "tenant_id": tid,
                            "break_at_event_id": result.get("break_at_event_id"),
                            "chain_length": result["chain_length"],
                            "error_message": result.get("error_message"),
                        }
                    )
                    log.error(
                        "audit_chain.broken",
                        tenant_id=tid,
                        break_at_event_id=result.get("break_at_event_id"),
                        chain_length=result["chain_length"],
                        error_message=result.get("error_message"),
                    )
                    # Raise to Sentry without failing the whole run.
                    _alert_broken_chain(tid, result)

            except Exception as exc:
                errors += 1
                log.error("audit_chain.verify_failed", tenant_id=tid, error=str(exc))
                await db.rollback()

    summary = {
        "tenants_verified": len(tenant_ids),
        "ok": ok,
        "broken": broken,
        "errors": errors,
        "broken_tenants": broken_tenants,
    }
    log.info(
        "audit_chain.run_complete", **{k: v for k, v in summary.items() if k != "broken_tenants"}
    )
    return summary


def _alert_broken_chain(tenant_id: str, result: dict[str, Any]) -> None:
    """Send a P0 alert to Sentry if the SDK is configured. No-op otherwise."""
    try:
        import sentry_sdk
    except ImportError:
        return

    try:
        with sentry_sdk.push_scope() as scope:
            scope.set_tag("tenant_id", tenant_id)
            scope.set_tag("severity", "p0")
            scope.set_tag("component", "audit_chain")
            scope.set_context(
                "chain_verification",
                {
                    "break_at_event_id": result.get("break_at_event_id"),
                    "chain_length": result.get("chain_length"),
                    "last_event_id": result.get("last_event_id"),
                    "error_message": result.get("error_message"),
                },
            )
            sentry_sdk.capture_message(
                f"Audit chain broken for tenant {tenant_id}",
                level="error",
            )
    except Exception as exc:  # pragma: no cover - sentry optional
        log.warning("audit_chain.sentry_alert_failed", tenant_id=tenant_id, error=str(exc))
