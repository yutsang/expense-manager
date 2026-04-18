"""Projects & Time Tracking API (Issue #67)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, HTTPException, Query, status

from app.api.v1.deps import ActorId, DbSession, TenantId
from app.api.v1.schemas import (
    BillingRateCreate,
    BillingRateListResponse,
    BillingRateResponse,
    GenerateInvoiceRequest,
    InvoiceResponse,
    ProjectCreate,
    ProjectListResponse,
    ProjectResponse,
    ProjectUpdate,
    TimeEntryCreate,
    TimeEntryListResponse,
    TimeEntryResponse,
    TimeEntryUpdate,
    WipResponse,
)
from app.services.invoices import get_invoice_lines
from app.services.projects import (
    NoUnbilledEntriesError,
    ProjectNotFoundError,
    TimeEntryLockedError,
    TimeEntryNotFoundError,
    create_billing_rate,
    create_project,
    create_time_entry,
    generate_invoice,
    get_project,
    get_wip,
    list_billing_rates,
    list_projects,
    list_time_entries,
    update_project,
    update_time_entry,
)

router = APIRouter(prefix="/projects", tags=["projects"])


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create(body: ProjectCreate, db: DbSession, tenant_id: TenantId, actor_id: ActorId):
    try:
        proj = await create_project(
            db,
            tenant_id,
            actor_id,
            contact_id=body.contact_id,
            name=body.name,
            code=body.code,
            description=body.description,
            status=body.status,
            budget_hours=Decimal(body.budget_hours) if body.budget_hours else None,
            budget_amount=Decimal(body.budget_amount) if body.budget_amount else None,
            currency=body.currency,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    await db.commit()
    await db.refresh(proj)
    return ProjectResponse.model_validate(proj)


@router.get("", response_model=ProjectListResponse)
async def list_all(
    db: DbSession,
    tenant_id: TenantId,
    proj_status: str | None = Query(default=None, alias="status"),
    contact_id: str | None = Query(default=None),
    limit: int = Query(default=50, le=200),
    cursor: str | None = Query(default=None),
):
    items = await list_projects(
        db, tenant_id, status=proj_status, contact_id=contact_id, limit=limit + 1, cursor=cursor
    )
    next_cursor = None
    if len(items) > limit:
        next_cursor = items[limit].id
        items = items[:limit]
    return ProjectListResponse(
        items=[ProjectResponse.model_validate(p) for p in items],
        next_cursor=next_cursor,
    )


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_one(project_id: str, db: DbSession, tenant_id: TenantId):
    try:
        proj = await get_project(db, tenant_id, project_id)
        return ProjectResponse.model_validate(proj)
    except ProjectNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Project not found")


@router.patch("/{project_id}", response_model=ProjectResponse)
async def update(
    project_id: str,
    body: ProjectUpdate,
    db: DbSession,
    tenant_id: TenantId,
    actor_id: ActorId,
):
    try:
        proj = await update_project(
            db,
            tenant_id,
            project_id,
            actor_id,
            name=body.name,
            code=body.code,
            description=body.description,
            status=body.status,
            budget_hours=Decimal(body.budget_hours) if body.budget_hours else None,
            budget_amount=Decimal(body.budget_amount) if body.budget_amount else None,
            currency=body.currency,
        )
        await db.commit()
        await db.refresh(proj)
        return ProjectResponse.model_validate(proj)
    except ProjectNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Project not found")
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# Time Entries
# ---------------------------------------------------------------------------

time_entries_router = APIRouter(prefix="/time-entries", tags=["time-entries"])


@time_entries_router.post(
    "", response_model=TimeEntryResponse, status_code=status.HTTP_201_CREATED
)
async def create_entry(
    body: TimeEntryCreate, db: DbSession, tenant_id: TenantId, actor_id: ActorId
):
    try:
        te = await create_time_entry(
            db,
            tenant_id,
            actor_id,
            project_id=body.project_id,
            user_id=body.user_id,
            entry_date=body.entry_date,
            hours=Decimal(body.hours),
            description=body.description,
            is_billable=body.is_billable,
        )
    except (ProjectNotFoundError, ValueError) as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    await db.commit()
    await db.refresh(te)
    return TimeEntryResponse.model_validate(te)


@time_entries_router.get("", response_model=TimeEntryListResponse)
async def list_entries(
    db: DbSession,
    tenant_id: TenantId,
    project_id: str | None = Query(default=None),
    user_id: str | None = Query(default=None),
    from_date: date | None = Query(default=None),
    to_date: date | None = Query(default=None),
    is_billable: bool | None = Query(default=None),
    approval_status: str | None = Query(default=None),
    limit: int = Query(default=50, le=200),
    cursor: str | None = Query(default=None),
):
    items = await list_time_entries(
        db,
        tenant_id,
        project_id=project_id,
        user_id=user_id,
        from_date=from_date,
        to_date=to_date,
        is_billable=is_billable,
        approval_status=approval_status,
        limit=limit + 1,
        cursor=cursor,
    )
    next_cursor = None
    if len(items) > limit:
        next_cursor = items[limit].id
        items = items[:limit]
    return TimeEntryListResponse(
        items=[TimeEntryResponse.model_validate(te) for te in items],
        next_cursor=next_cursor,
    )


@time_entries_router.patch("/{entry_id}", response_model=TimeEntryResponse)
async def update_entry(
    entry_id: str,
    body: TimeEntryUpdate,
    db: DbSession,
    tenant_id: TenantId,
    actor_id: ActorId,
):
    try:
        te = await update_time_entry(
            db,
            tenant_id,
            entry_id,
            actor_id,
            hours=Decimal(body.hours) if body.hours else None,
            description=body.description,
            is_billable=body.is_billable,
            approval_status=body.approval_status,
            entry_date=body.entry_date,
        )
        await db.commit()
        await db.refresh(te)
        return TimeEntryResponse.model_validate(te)
    except TimeEntryNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Time entry not found")
    except TimeEntryLockedError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# Billing Rates
# ---------------------------------------------------------------------------

billing_rates_router = APIRouter(prefix="/billing-rates", tags=["billing-rates"])


@billing_rates_router.post(
    "", response_model=BillingRateResponse, status_code=status.HTTP_201_CREATED
)
async def create_rate(
    body: BillingRateCreate, db: DbSession, tenant_id: TenantId, actor_id: ActorId
):
    try:
        br = await create_billing_rate(
            db,
            tenant_id,
            actor_id,
            rate=Decimal(body.rate),
            effective_from=body.effective_from,
            effective_to=body.effective_to,
            project_id=body.project_id,
            user_id=body.user_id,
            role=body.role,
            currency=body.currency,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    await db.commit()
    await db.refresh(br)
    return BillingRateResponse.model_validate(br)


@billing_rates_router.get("", response_model=BillingRateListResponse)
async def list_rates(
    db: DbSession,
    tenant_id: TenantId,
    project_id: str | None = Query(default=None),
    limit: int = Query(default=50, le=200),
    cursor: str | None = Query(default=None),
):
    items = await list_billing_rates(
        db, tenant_id, project_id=project_id, limit=limit + 1, cursor=cursor
    )
    next_cursor = None
    if len(items) > limit:
        next_cursor = items[limit].id
        items = items[:limit]
    return BillingRateListResponse(
        items=[BillingRateResponse.model_validate(br) for br in items],
        next_cursor=next_cursor,
    )


# ---------------------------------------------------------------------------
# Invoice generation & WIP
# ---------------------------------------------------------------------------


@router.post("/{project_id}/generate-invoice", response_model=InvoiceResponse)
async def gen_invoice(
    project_id: str,
    body: GenerateInvoiceRequest,
    db: DbSession,
    tenant_id: TenantId,
    actor_id: ActorId,
):
    try:
        inv = await generate_invoice(
            db, tenant_id, actor_id, project_id, body.from_date, body.to_date
        )
        await db.commit()
        await db.refresh(inv)
        lines = await get_invoice_lines(db, inv.id)
        return InvoiceResponse.model_validate({**inv.__dict__, "lines": lines})
    except ProjectNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Project not found")
    except NoUnbilledEntriesError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.get("/{project_id}/wip", response_model=WipResponse)
async def wip(project_id: str, db: DbSession, tenant_id: TenantId):
    try:
        return await get_wip(db, tenant_id, project_id)
    except ProjectNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Project not found")
