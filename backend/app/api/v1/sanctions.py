"""Sanctions API — manual refresh trigger, snapshot status, screen single contact."""
from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, HTTPException, status
from sqlalchemy import select

from app.api.v1.deps import DbSession, TenantId
from app.api.v1.schemas import ContactScreeningResultResponse, SanctionsSnapshotResponse
from app.infra.models import Contact
from app.services.sanctions import (
    get_latest_snapshots,
    get_screening_result,
    refresh_fatf,
    refresh_ofac,
    screen_contact,
)

router = APIRouter(prefix="/sanctions", tags=["sanctions"])


@router.get("/snapshots", response_model=list[SanctionsSnapshotResponse])
async def list_snapshots(db: DbSession) -> list[SanctionsSnapshotResponse]:
    """List all currently active sanctions list snapshots."""
    snaps = await get_latest_snapshots(db)
    return [SanctionsSnapshotResponse.model_validate(s) for s in snaps]


@router.post("/refresh", status_code=status.HTTP_202_ACCEPTED)
async def trigger_refresh(
    db: DbSession,
    background_tasks: BackgroundTasks,
) -> dict[str, str]:
    """Trigger an immediate sanctions list refresh (runs in background)."""

    async def _do_refresh() -> None:
        try:
            await refresh_ofac(db)
        except Exception as exc:  # noqa: BLE001
            pass  # errors logged inside service
        try:
            await refresh_fatf(db)
        except Exception as exc:  # noqa: BLE001
            pass
        await db.commit()

    background_tasks.add_task(_do_refresh)
    return {"status": "refresh_queued"}


@router.post("/screen/{contact_id}", response_model=ContactScreeningResultResponse)
async def screen_contact_now(
    contact_id: str,
    db: DbSession,
    tenant_id: TenantId,
) -> ContactScreeningResultResponse:
    """Screen a specific contact against current sanctions lists."""
    contact = await db.scalar(
        select(Contact).where(
            Contact.id == contact_id,
            Contact.tenant_id == tenant_id,
        )
    )
    if not contact:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Contact not found")
    result = await screen_contact(
        db,
        contact_id=contact_id,
        tenant_id=tenant_id,
        contact_name=contact.name,
        contact_country=contact.country,
    )
    await db.commit()
    return ContactScreeningResultResponse.model_validate(result)


@router.get("/screen/{contact_id}", response_model=ContactScreeningResultResponse | None)
async def get_screen_result(
    contact_id: str,
    db: DbSession,
    tenant_id: TenantId,
) -> ContactScreeningResultResponse | None:
    """Get the current screening result for a contact."""
    result = await get_screening_result(db, contact_id=contact_id, tenant_id=tenant_id)
    if not result:
        return None
    return ContactScreeningResultResponse.model_validate(result)
