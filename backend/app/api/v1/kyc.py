"""KYC / Sanctions API — list, get, upsert, dashboard alerts, UBO management."""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, HTTPException, status

from app.api.v1.deps import ActorId, DbSession, TenantId
from app.api.v1.schemas import (
    ContactKycResponse,
    ContactKycUpdate,
    ContactUBOCreate,
    ContactUBOResponse,
    ContactUBOUpdate,
    KycDashboardAlerts,
    KycListItem,
)
from app.services.kyc import (
    KycNotFoundError,
    UBONotFoundError,
    create_ubo,
    get_dashboard_alerts,
    get_or_create_kyc,
    list_kyc_summary,
    list_ubos,
    update_kyc,
    update_ubo,
)

router = APIRouter(prefix="/kyc", tags=["kyc"])


@router.get("/dashboard-alerts", response_model=KycDashboardAlerts)
async def dashboard_alerts(db: DbSession, tenant_id: TenantId) -> KycDashboardAlerts:
    counts = await get_dashboard_alerts(db, tenant_id=tenant_id)
    return KycDashboardAlerts(**counts)


@router.get("", response_model=list[KycListItem])
async def list_kyc(db: DbSession, tenant_id: TenantId) -> list[KycListItem]:
    rows = await list_kyc_summary(db, tenant_id=tenant_id)
    return [KycListItem(**row) for row in rows]


@router.get("/{contact_id}", response_model=ContactKycResponse)
async def get_kyc(contact_id: str, db: DbSession, tenant_id: TenantId) -> ContactKycResponse:
    try:
        kyc = await get_or_create_kyc(db, contact_id=contact_id, tenant_id=tenant_id)
        await db.commit()
        return ContactKycResponse.model_validate(kyc)
    except Exception as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.put("/{contact_id}", response_model=ContactKycResponse)
async def upsert_kyc(
    contact_id: str,
    body: ContactKycUpdate,
    db: DbSession,
    tenant_id: TenantId,
    actor_id: ActorId,
) -> ContactKycResponse:
    fields = {k: v for k, v in body.model_dump().items() if v is not None}
    fields["updated_by"] = actor_id
    try:
        kyc = await update_kyc(db, contact_id=contact_id, tenant_id=tenant_id, **fields)
        await db.commit()
        return ContactKycResponse.model_validate(kyc)
    except KycNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


# ── UBO (Ultimate Beneficial Owner) endpoints — Cap 622 ─────────────────────


@router.get(
    "/contacts/{contact_id}/ubos",
    response_model=list[ContactUBOResponse],
    tags=["kyc", "ubo"],
)
async def list_contact_ubos(
    contact_id: str,
    db: DbSession,
    tenant_id: TenantId,
) -> list[ContactUBOResponse]:
    """GET /v1/contacts/{contact_id}/ubos — list UBO records for a contact."""
    ubos = await list_ubos(db, contact_id=contact_id, tenant_id=tenant_id)
    return [ContactUBOResponse.model_validate(u) for u in ubos]


@router.post(
    "/contacts/{contact_id}/ubos",
    response_model=ContactUBOResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["kyc", "ubo"],
)
async def create_contact_ubo(
    contact_id: str,
    body: ContactUBOCreate,
    db: DbSession,
    tenant_id: TenantId,
    actor_id: ActorId,
) -> ContactUBOResponse:
    """POST /v1/contacts/{contact_id}/ubos — create a new UBO record."""
    ubo = await create_ubo(
        db,
        tenant_id=tenant_id,
        contact_id=contact_id,
        controller_name=body.controller_name,
        id_type=body.id_type,
        id_number=body.id_number,
        nationality=body.nationality,
        address=body.address,
        ownership_pct=Decimal(body.ownership_pct),
        control_type=body.control_type,
        is_significant_controller=body.is_significant_controller,
        effective_date=body.effective_date,
        ceased_date=body.ceased_date,
    )
    await db.commit()
    return ContactUBOResponse.model_validate(ubo)


@router.patch(
    "/contacts/{contact_id}/ubos/{ubo_id}",
    response_model=ContactUBOResponse,
    tags=["kyc", "ubo"],
)
async def patch_contact_ubo(
    contact_id: str,
    ubo_id: str,
    body: ContactUBOUpdate,
    db: DbSession,
    tenant_id: TenantId,
    actor_id: ActorId,
) -> ContactUBOResponse:
    """PATCH /v1/contacts/{contact_id}/ubos/{ubo_id} — update UBO fields."""
    fields = {k: v for k, v in body.model_dump().items() if v is not None}
    if "ownership_pct" in fields:
        fields["ownership_pct"] = Decimal(fields["ownership_pct"])
    fields["updated_by"] = actor_id
    try:
        ubo = await update_ubo(db, ubo_id=ubo_id, tenant_id=tenant_id, **fields)
        await db.commit()
        return ContactUBOResponse.model_validate(ubo)
    except UBONotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
