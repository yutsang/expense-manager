"""Sanctions API — manual refresh trigger, snapshot status, entry search, screen contact."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, status
from sqlalchemy import func, or_, select

from app.api.v1.deps import DbSession, TenantId
from app.api.v1.schemas import (
    ContactScreeningResultResponse,
    SanctionsEntryListResponse,
    SanctionsEntryResponse,
    SanctionsSnapshotResponse,
)
from app.infra.models import Contact, SanctionsListEntry, SanctionsListSnapshot
from app.services.sanctions import (
    get_latest_snapshots,
    get_screening_result,
    refresh_additional_lists,
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
        try:  # noqa: SIM105
            await refresh_ofac(db)
        except Exception:  # noqa: BLE001, S110
            pass  # errors logged inside service
        try:  # noqa: SIM105
            await refresh_fatf(db)
        except Exception:  # noqa: BLE001, S110
            pass
        try:  # noqa: SIM105
            await refresh_additional_lists(db)
        except Exception:  # noqa: BLE001, S110
            pass  # errors logged inside service
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


@router.get("/entries", response_model=SanctionsEntryListResponse)
async def search_entries(
    db: DbSession,
    q: str | None = Query(default=None, description="Name search (case-insensitive)"),
    source: str | None = Query(
        default=None,
        description=(
            "Filter by source: ofac_consolidated | fatf_blacklist | fatf_greylist | "
            "opensanctions_pep | opensanctions_default"
        ),
    ),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
) -> SanctionsEntryListResponse:
    """Search sanctions list entries across active snapshots."""
    # active snapshot IDs
    snap_ids_result = await db.execute(
        select(SanctionsListSnapshot.id).where(SanctionsListSnapshot.is_active.is_(True))
    )
    snap_ids = [row[0] for row in snap_ids_result.all()]
    if not snap_ids:
        return SanctionsEntryListResponse(items=[], total=0)

    base = select(SanctionsListEntry).where(SanctionsListEntry.snapshot_id.in_(snap_ids))
    count_base = select(func.count(SanctionsListEntry.id)).where(
        SanctionsListEntry.snapshot_id.in_(snap_ids)
    )

    if source:
        base = base.where(SanctionsListEntry.source == source)
        count_base = count_base.where(SanctionsListEntry.source == source)

    if q:
        from sqlalchemy import text

        pattern = f"%{q}%"
        # Search primary_name, ref_id, and any alias name inside the JSONB array
        alias_subquery = text(
            "EXISTS (SELECT 1 FROM jsonb_array_elements(sanctions_list_entries.aliases) AS a "
            "WHERE a->>'name' ILIKE :pat)"
        ).bindparams(pat=pattern)
        name_filter = or_(
            SanctionsListEntry.primary_name.ilike(pattern),
            SanctionsListEntry.ref_id.ilike(pattern),
            alias_subquery,
        )
        base = base.where(name_filter)
        count_base = count_base.where(name_filter)

    total = await db.scalar(count_base) or 0
    rows = await db.execute(
        base.order_by(SanctionsListEntry.primary_name).offset(offset).limit(limit)
    )
    entries = list(rows.scalars())
    return SanctionsEntryListResponse(
        items=[SanctionsEntryResponse.model_validate(e) for e in entries],
        total=total,
    )


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
