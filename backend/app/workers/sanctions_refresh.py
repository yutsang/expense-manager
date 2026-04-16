"""ARQ worker: daily sanctions list refresh + contact re-screening."""

from __future__ import annotations

from typing import Any

from sqlalchemy import distinct, select

from app.core.db import AsyncSessionLocal
from app.core.logging import get_logger
from app.core.tenant import set_rls_tenant
from app.infra.models import Contact
from app.services.sanctions import (
    refresh_additional_lists,
    refresh_fatf,
    refresh_ofac,
    screen_all_contacts,
)

log = get_logger(__name__)


async def refresh_sanctions_lists(ctx: dict[str, Any]) -> dict[str, Any]:
    """Fetch OFAC + FATF + UN + UK OFSI + EU lists, store snapshots, screen all contacts."""
    ofac_changed = False
    fatf_changed = False
    additional_changed = False

    async with AsyncSessionLocal() as db:
        # OFAC
        try:
            ofac_snap, ofac_changed = await refresh_ofac(db)
            log.info("sanctions.ofac_refreshed", changed=ofac_changed, count=ofac_snap.entry_count)
        except Exception as exc:
            log.error("sanctions.ofac_refresh_failed", error=str(exc))

        # FATF
        try:
            fatf_results = await refresh_fatf(db)
            fatf_changed = any(changed for _, changed in fatf_results)
        except Exception as exc:
            log.error("sanctions.fatf_refresh_failed", error=str(exc))

        # UN, UK OFSI, EU
        try:
            additional_results = await refresh_additional_lists(db)
            additional_changed = any(changed for _, changed in additional_results)
        except Exception as exc:
            log.error("sanctions.additional_refresh_failed", error=str(exc))

        await db.commit()

    results: dict[str, Any] = {
        "ofac_changed": ofac_changed,
        "fatf_changed": fatf_changed,
        "additional_changed": additional_changed,
        "tenants_screened": 0,
    }

    if not (ofac_changed or fatf_changed or additional_changed):
        return results

    # Screen all tenants — discover tenant_ids from contacts table
    async with AsyncSessionLocal() as db:
        tenant_rows = await db.execute(select(distinct(Contact.tenant_id)))
        tenant_ids = [row[0] for row in tenant_rows.all()]

    for tid in tenant_ids:
        async with AsyncSessionLocal() as db:
            await set_rls_tenant(db, tid)
            try:
                counts = await screen_all_contacts(db, tenant_id=tid)
                await db.commit()
                log.info("sanctions.tenant_screened", tenant_id=tid, counts=counts)
                results["tenants_screened"] += 1
            except Exception as exc:
                log.error("sanctions.tenant_screen_failed", tenant_id=tid, error=str(exc))
                await db.rollback()

    return results
