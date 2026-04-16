"""KYC / Sanctions API — list, get, upsert, dashboard alerts."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.api.v1.deps import ActorId, DbSession, TenantId
from app.api.v1.schemas import (
    ContactKycResponse,
    ContactKycUpdate,
    KycDashboardAlerts,
    KycListItem,
)
from app.services.kyc import (
    KycNotFoundError,
    get_dashboard_alerts,
    get_or_create_kyc,
    list_kyc_summary,
    update_kyc,
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
