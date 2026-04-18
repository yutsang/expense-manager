"""Multi-entity consolidation API — group management and consolidated reports."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.api.v1.deps import ActorId, DbSession, TenantId
from app.services.consolidation import (
    DuplicateMemberError,
    EntityGroupNotFoundError,
    add_member,
    create_group,
    delete_group,
    get_consolidated_bs,
    get_consolidated_pnl,
    get_group,
    list_groups,
    list_members,
    remove_member,
)

router = APIRouter(prefix="/consolidation", tags=["consolidation"])


# ── Schemas ──────────────────────────────────────────────────────────────────


class EntityGroupCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)


class EntityGroupResponse(BaseModel):
    id: str
    parent_tenant_id: str
    name: str
    created_at: Any
    updated_at: Any

    model_config = {"from_attributes": True}


class EntityGroupMemberCreate(BaseModel):
    member_tenant_id: str
    ownership_pct: str = Field(default="100", description="Ownership percentage (0-100)")

    @classmethod
    def validate_ownership(cls, v: str) -> str:
        d = Decimal(v)
        if d <= 0 or d > 100:
            raise ValueError("ownership_pct must be between 0 and 100 (exclusive of 0)")
        return v


class EntityGroupMemberResponse(BaseModel):
    id: str
    group_id: str
    member_tenant_id: str
    ownership_pct: str
    created_at: Any
    updated_at: Any

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm_member(cls, m: object) -> EntityGroupMemberResponse:
        return cls.model_validate(m)


class ConsolidatedPLLineResponse(BaseModel):
    account_code: str
    account_name: str
    subtype: str
    per_entity: dict[str, str]
    total: str


class ConsolidatedPLResponse(BaseModel):
    from_date: date
    to_date: date
    group_id: str
    group_name: str
    total_revenue: str
    total_expenses: str
    net_profit: str
    revenue_lines: list[ConsolidatedPLLineResponse]
    expense_lines: list[ConsolidatedPLLineResponse]
    member_names: dict[str, str]
    generated_at: Any


class ConsolidatedBSLineResponse(BaseModel):
    account_code: str
    account_name: str
    subtype: str
    per_entity: dict[str, str]
    total: str


class ConsolidatedBSSectionResponse(BaseModel):
    total: str
    lines: list[ConsolidatedBSLineResponse]


class ConsolidatedBSResponse(BaseModel):
    as_of: date
    group_id: str
    group_name: str
    assets: ConsolidatedBSSectionResponse
    liabilities: ConsolidatedBSSectionResponse
    equity: ConsolidatedBSSectionResponse
    total_liabilities_and_equity: str
    is_balanced: bool
    member_names: dict[str, str]
    generated_at: Any


# ── Group endpoints ──────────────────────────────────────────────────────────


@router.post("/groups", response_model=EntityGroupResponse, status_code=status.HTTP_201_CREATED)
async def create_group_endpoint(
    body: EntityGroupCreate,
    db: DbSession,
    tenant_id: TenantId,
    actor_id: ActorId,
) -> EntityGroupResponse:
    group = await create_group(
        db, parent_tenant_id=tenant_id, name=body.name, actor_id=actor_id
    )
    await db.commit()
    return EntityGroupResponse.model_validate(group)


@router.get("/groups", response_model=list[EntityGroupResponse])
async def list_groups_endpoint(
    db: DbSession,
    tenant_id: TenantId,
) -> list[EntityGroupResponse]:
    groups = await list_groups(db, parent_tenant_id=tenant_id)
    return [EntityGroupResponse.model_validate(g) for g in groups]


@router.get("/groups/{group_id}", response_model=EntityGroupResponse)
async def get_group_endpoint(
    group_id: str,
    db: DbSession,
    tenant_id: TenantId,
) -> EntityGroupResponse:
    try:
        group = await get_group(db, group_id=group_id, parent_tenant_id=tenant_id)
    except EntityGroupNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return EntityGroupResponse.model_validate(group)


@router.delete("/groups/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_group_endpoint(
    group_id: str,
    db: DbSession,
    tenant_id: TenantId,
) -> None:
    try:
        await delete_group(db, group_id=group_id, parent_tenant_id=tenant_id)
    except EntityGroupNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    await db.commit()


# ── Member endpoints ─────────────────────────────────────────────────────────


@router.post(
    "/groups/{group_id}/members",
    response_model=EntityGroupMemberResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_member_endpoint(
    group_id: str,
    body: EntityGroupMemberCreate,
    db: DbSession,
    tenant_id: TenantId,
    actor_id: ActorId,
) -> EntityGroupMemberResponse:
    try:
        member = await add_member(
            db,
            group_id=group_id,
            parent_tenant_id=tenant_id,
            member_tenant_id=body.member_tenant_id,
            ownership_pct=Decimal(body.ownership_pct),
            actor_id=actor_id,
        )
    except EntityGroupNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except DuplicateMemberError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    await db.commit()
    return EntityGroupMemberResponse.model_validate(member)


@router.get("/groups/{group_id}/members", response_model=list[EntityGroupMemberResponse])
async def list_members_endpoint(
    group_id: str,
    db: DbSession,
    tenant_id: TenantId,
) -> list[EntityGroupMemberResponse]:
    try:
        members = await list_members(db, group_id=group_id, parent_tenant_id=tenant_id)
    except EntityGroupNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return [EntityGroupMemberResponse.model_validate(m) for m in members]


# ── Report endpoints ─────────────────────────────────────────────────────────


@router.get("/reports/pnl", response_model=ConsolidatedPLResponse)
async def consolidated_pnl_endpoint(
    db: DbSession,
    tenant_id: TenantId,
    group_id: str = Query(...),
    from_date: date = Query(..., alias="from"),
    to_date: date = Query(..., alias="to"),
) -> ConsolidatedPLResponse:
    if from_date > to_date:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="from must be on or before to",
        )
    try:
        report = await get_consolidated_pnl(
            db,
            group_id=group_id,
            parent_tenant_id=tenant_id,
            from_date=from_date,
            to_date=to_date,
        )
    except EntityGroupNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    def _fmt_pl_line(ln: object) -> ConsolidatedPLLineResponse:
        return ConsolidatedPLLineResponse(
            account_code=ln.account_code,
            account_name=ln.account_name,
            subtype=ln.subtype,
            per_entity={k: f"{v:.2f}" for k, v in ln.per_entity.items()},
            total=f"{ln.total:.2f}",
        )

    return ConsolidatedPLResponse(
        from_date=report.from_date,
        to_date=report.to_date,
        group_id=report.group_id,
        group_name=report.group_name,
        total_revenue=f"{report.total_revenue:.2f}",
        total_expenses=f"{report.total_expenses:.2f}",
        net_profit=f"{report.net_profit:.2f}",
        revenue_lines=[_fmt_pl_line(ln) for ln in report.revenue_lines],
        expense_lines=[_fmt_pl_line(ln) for ln in report.expense_lines],
        member_names=report.member_names,
        generated_at=report.generated_at,
    )


@router.get("/reports/bs", response_model=ConsolidatedBSResponse)
async def consolidated_bs_endpoint(
    db: DbSession,
    tenant_id: TenantId,
    group_id: str = Query(...),
    as_of: date = Query(...),
) -> ConsolidatedBSResponse:
    try:
        report = await get_consolidated_bs(
            db,
            group_id=group_id,
            parent_tenant_id=tenant_id,
            as_of=as_of,
        )
    except EntityGroupNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    def _fmt_bs_line(ln: object) -> ConsolidatedBSLineResponse:
        return ConsolidatedBSLineResponse(
            account_code=ln.account_code,
            account_name=ln.account_name,
            subtype=ln.subtype,
            per_entity={k: f"{v:.2f}" for k, v in ln.per_entity.items()},
            total=f"{ln.total:.2f}",
        )

    def _fmt_section(section: object) -> ConsolidatedBSSectionResponse:
        return ConsolidatedBSSectionResponse(
            total=f"{section.total:.2f}",
            lines=[_fmt_bs_line(ln) for ln in section.lines],
        )

    return ConsolidatedBSResponse(
        as_of=report.as_of,
        group_id=report.group_id,
        group_name=report.group_name,
        assets=_fmt_section(report.assets),
        liabilities=_fmt_section(report.liabilities),
        equity=_fmt_section(report.equity),
        total_liabilities_and_equity=f"{report.total_liabilities_and_equity:.2f}",
        is_balanced=report.is_balanced,
        member_names=report.member_names,
        generated_at=report.generated_at,
    )
