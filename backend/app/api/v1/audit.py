"""Audit API — event timeline, chain verification, sampling, JE testing, evidence packages."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.api.v1.deps import ActorId, DbSession, TenantId
from app.services import audit as audit_svc
from app.services.evidence_package import build_evidence_package

router = APIRouter(prefix="/audit", tags=["audit"])


# ---------------------------------------------------------------------------
# Pydantic response/request schemas (local — no shared schemas file needed)
# ---------------------------------------------------------------------------


class AuditEventResponse(BaseModel):
    id: str
    tenant_id: str | None
    occurred_at: datetime
    actor_type: str
    actor_id: str | None
    session_id: str | None
    ip: str | None
    user_agent: str | None
    action: str
    entity_type: str
    entity_id: str | None
    before_state: dict[str, Any] | None = None
    after_state: dict[str, Any] | None = None
    metadata_: dict[str, Any] = Field(default_factory=dict, alias="metadata_")

    model_config = {"from_attributes": True, "populate_by_name": True}


class AuditEventListResponse(BaseModel):
    items: list[AuditEventResponse]
    next_cursor: str | None = None


class ChainVerificationResponse(BaseModel):
    id: str | None = None
    is_valid: bool
    chain_length: int
    last_event_id: str | None
    break_at_event_id: str | None
    error_message: str | None
    verified_at: datetime


class ChainVerificationHistoryResponse(BaseModel):
    latest: ChainVerificationResponse | None
    history: list[ChainVerificationResponse]


class ChainVerificationRecord(BaseModel):
    id: str
    tenant_id: str
    verified_at: datetime
    chain_length: int
    last_event_id: str | None
    is_valid: bool
    break_at_event_id: str | None
    error_message: str | None

    model_config = {"from_attributes": True}


class SampleRequest(BaseModel):
    method: str = Field(..., pattern="^(random|monetary_unit|stratified)$")
    size: int = Field(..., ge=1, le=500)
    seed: int
    from_date: date | None = None
    to_date: date | None = None


class SampleResponse(BaseModel):
    method: str
    size: int
    seed: int
    entries: list[dict[str, Any]]


class JeTestingResponse(BaseModel):
    cutoff_entries: list[dict[str, Any]]
    weekend_holiday_posts: list[dict[str, Any]]
    round_number_entries: list[dict[str, Any]]
    large_entries: list[dict[str, Any]]
    reversed_same_day: list[dict[str, Any]]


class ReportSnapshotCreate(BaseModel):
    report_type: str = Field(..., max_length=50)
    params: dict[str, Any] = Field(default_factory=dict)
    data: dict[str, Any]


class ReportSnapshotResponse(BaseModel):
    id: str
    tenant_id: str
    report_type: str
    params: dict[str, Any]
    generated_at: datetime
    sha256: str
    created_by: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ReportSnapshotListResponse(BaseModel):
    items: list[ReportSnapshotResponse]
    next_cursor: str | None = None


class EvidencePackageRequest(BaseModel):
    from_date: date
    to_date: date


# ---------------------------------------------------------------------------
# Audit event endpoints
# ---------------------------------------------------------------------------


@router.get("/events", response_model=AuditEventListResponse)
async def list_events(
    db: DbSession,
    tenant_id: TenantId,
    actor_id_filter: str | None = Query(default=None, alias="actor_id"),
    action: str | None = Query(default=None),
    entity_type: str | None = Query(default=None),
    entity_id: str | None = Query(default=None),
    from_dt: datetime | None = Query(default=None),
    to_dt: datetime | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    cursor: str | None = Query(default=None),
) -> AuditEventListResponse:
    events, next_cursor = await audit_svc.list_audit_events(
        db,
        tenant_id,
        actor_id=actor_id_filter,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        from_dt=from_dt,
        to_dt=to_dt,
        limit=limit,
        cursor=cursor,
    )
    return AuditEventListResponse(
        items=[AuditEventResponse.model_validate(e) for e in events],
        next_cursor=next_cursor,
    )


@router.get("/events/{event_id}", response_model=AuditEventResponse)
async def get_event(
    event_id: str,
    db: DbSession,
    tenant_id: TenantId,
) -> AuditEventResponse:
    event = await audit_svc.get_audit_event(db, event_id, tenant_id)
    if event is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Audit event not found")
    return AuditEventResponse.model_validate(event)


# ---------------------------------------------------------------------------
# Chain verification
# ---------------------------------------------------------------------------


@router.get("/chain-verification", response_model=ChainVerificationHistoryResponse)
async def get_chain_verification(
    db: DbSession,
    tenant_id: TenantId,
) -> ChainVerificationHistoryResponse:
    history_records = await audit_svc.get_chain_verification_history(db, tenant_id, limit=10)
    history = [ChainVerificationRecord.model_validate(r) for r in history_records]

    def _to_response(r: ChainVerificationRecord) -> ChainVerificationResponse:
        return ChainVerificationResponse(
            id=r.id,
            is_valid=r.is_valid,
            chain_length=r.chain_length,
            last_event_id=r.last_event_id,
            break_at_event_id=r.break_at_event_id,
            error_message=r.error_message,
            verified_at=r.verified_at,
        )

    latest = _to_response(history[0]) if history else None
    return ChainVerificationHistoryResponse(
        latest=latest,
        history=[_to_response(r) for r in history],
    )


@router.post("/chain-verification", response_model=ChainVerificationResponse, status_code=status.HTTP_201_CREATED)
async def trigger_chain_verification(
    db: DbSession,
    tenant_id: TenantId,
    actor_id: ActorId,
) -> ChainVerificationResponse:
    if not actor_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="X-Actor-ID required")
    result = await audit_svc.verify_chain(db, tenant_id)
    await db.commit()
    return ChainVerificationResponse(
        id=result.get("id"),
        is_valid=result["is_valid"],
        chain_length=result["chain_length"],
        last_event_id=result.get("last_event_id"),
        break_at_event_id=result.get("break_at_event_id"),
        error_message=result.get("error_message"),
        verified_at=result["verified_at"],
    )


# ---------------------------------------------------------------------------
# Sampling
# ---------------------------------------------------------------------------


@router.post("/samples", response_model=SampleResponse)
async def create_sample(
    body: SampleRequest,
    db: DbSession,
    tenant_id: TenantId,
) -> SampleResponse:
    entries = await audit_svc.sample_journal_entries(
        db,
        tenant_id,
        method=body.method,
        size=body.size,
        seed=body.seed,
        from_date=body.from_date,
        to_date=body.to_date,
    )
    return SampleResponse(method=body.method, size=body.size, seed=body.seed, entries=entries)


# ---------------------------------------------------------------------------
# JE testing
# ---------------------------------------------------------------------------


@router.get("/je-testing", response_model=JeTestingResponse)
async def je_testing(
    db: DbSession,
    tenant_id: TenantId,
    from_date: date = Query(...),
    to_date: date = Query(...),
) -> JeTestingResponse:
    report = await audit_svc.get_je_testing_report(db, tenant_id, from_date=from_date, to_date=to_date)
    return JeTestingResponse(**report)


# ---------------------------------------------------------------------------
# Evidence package
# ---------------------------------------------------------------------------


@router.post("/evidence-package")
async def create_evidence_package(
    body: EvidencePackageRequest,
    db: DbSession,
    tenant_id: TenantId,
    actor_id: ActorId,
) -> StreamingResponse:
    if not actor_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="X-Actor-ID required")

    zip_bytes = await build_evidence_package(
        db,
        tenant_id,
        from_date=body.from_date,
        to_date=body.to_date,
        created_by=actor_id,
    )
    await db.commit()

    filename = f"evidence_{tenant_id}_{body.from_date}_{body.to_date}.zip"
    return StreamingResponse(
        iter([zip_bytes]),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# Report snapshots
# ---------------------------------------------------------------------------


@router.get("/report-snapshots", response_model=ReportSnapshotListResponse)
async def list_snapshots(
    db: DbSession,
    tenant_id: TenantId,
    limit: int = Query(default=50, ge=1, le=200),
    cursor: str | None = Query(default=None),
) -> ReportSnapshotListResponse:
    snapshots, next_cursor = await audit_svc.list_report_snapshots(db, tenant_id, limit=limit, cursor=cursor)
    return ReportSnapshotListResponse(
        items=[ReportSnapshotResponse.model_validate(s) for s in snapshots],
        next_cursor=next_cursor,
    )


@router.post("/report-snapshots", response_model=ReportSnapshotResponse, status_code=status.HTTP_201_CREATED)
async def create_snapshot(
    body: ReportSnapshotCreate,
    db: DbSession,
    tenant_id: TenantId,
    actor_id: ActorId,
) -> ReportSnapshotResponse:
    if not actor_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="X-Actor-ID required")
    snapshot = await audit_svc.create_report_snapshot(
        db,
        tenant_id,
        report_type=body.report_type,
        params=body.params,
        data=body.data,
        created_by=actor_id,
    )
    await db.commit()
    return ReportSnapshotResponse.model_validate(snapshot)


@router.get("/report-snapshots/{snapshot_id}", response_model=ReportSnapshotResponse)
async def get_snapshot(
    snapshot_id: str,
    db: DbSession,
    tenant_id: TenantId,
) -> ReportSnapshotResponse:
    snapshot = await audit_svc.get_report_snapshot(db, snapshot_id, tenant_id)
    if snapshot is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report snapshot not found")
    return ReportSnapshotResponse.model_validate(snapshot)
