"""Approval Rules API — configurable approval workflow (Issue #61)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status

from app.api.v1.deps import ActorId, DbSession, TenantId
from app.api.v1.schemas import (
    ApprovalDelegationCreate,
    ApprovalDelegationListResponse,
    ApprovalDelegationResponse,
    ApprovalRuleCreate,
    ApprovalRuleListResponse,
    ApprovalRuleResponse,
    ApprovalRuleUpdate,
)
from app.services.approval_rules import (
    ApprovalDelegationError,
    ApprovalRuleNotFoundError,
    create_delegation,
    create_rule,
    delete_rule,
    get_rule,
    list_delegations,
    list_rules,
    update_rule,
)

router = APIRouter(prefix="/approval-rules", tags=["approval-rules"])


@router.get("", response_model=ApprovalRuleListResponse)
async def list_all(
    db: DbSession,
    tenant_id: TenantId,
    entity_type: str | None = Query(default=None),
):
    """List approval rules, optionally filtered by entity_type."""
    rules = await list_rules(db, tenant_id, entity_type=entity_type)
    return ApprovalRuleListResponse(items=[ApprovalRuleResponse.model_validate(r) for r in rules])


@router.post("", response_model=ApprovalRuleResponse, status_code=status.HTTP_201_CREATED)
async def create(body: ApprovalRuleCreate, db: DbSession, tenant_id: TenantId, actor_id: ActorId):
    """Create a new approval rule."""
    try:
        rule = await create_rule(
            db,
            tenant_id,
            actor_id,
            entity_type=body.entity_type,
            condition_field=body.condition_field,
            condition_operator=body.condition_operator,
            condition_value=body.condition_value,
            required_role=body.required_role,
            approval_order=body.approval_order,
            description=body.description,
        )
        await db.commit()
        await db.refresh(rule)
        return ApprovalRuleResponse.model_validate(rule)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.get("/{rule_id}", response_model=ApprovalRuleResponse)
async def get_one(rule_id: str, db: DbSession, tenant_id: TenantId):
    """Get a single approval rule."""
    try:
        rule = await get_rule(db, tenant_id, rule_id)
        return ApprovalRuleResponse.model_validate(rule)
    except ApprovalRuleNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Approval rule not found")


@router.patch("/{rule_id}", response_model=ApprovalRuleResponse)
async def update(
    rule_id: str, body: ApprovalRuleUpdate, db: DbSession, tenant_id: TenantId, actor_id: ActorId
):
    """Update an approval rule."""
    try:
        rule = await update_rule(
            db,
            tenant_id,
            actor_id,
            rule_id,
            entity_type=body.entity_type,
            condition_field=body.condition_field,
            condition_operator=body.condition_operator,
            condition_value=body.condition_value,
            required_role=body.required_role,
            approval_order=body.approval_order,
            description=body.description,
            is_active=body.is_active,
        )
        await db.commit()
        await db.refresh(rule)
        return ApprovalRuleResponse.model_validate(rule)
    except ApprovalRuleNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Approval rule not found")
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.delete("/{rule_id}", response_model=ApprovalRuleResponse)
async def deactivate(rule_id: str, db: DbSession, tenant_id: TenantId, actor_id: ActorId):
    """Deactivate an approval rule (soft-delete)."""
    try:
        rule = await delete_rule(db, tenant_id, actor_id, rule_id)
        await db.commit()
        await db.refresh(rule)
        return ApprovalRuleResponse.model_validate(rule)
    except ApprovalRuleNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Approval rule not found")


# ---------------------------------------------------------------------------
# Delegations
# ---------------------------------------------------------------------------


@router.get("/delegations/list", response_model=ApprovalDelegationListResponse)
async def list_all_delegations(db: DbSession, tenant_id: TenantId):
    """List active approval delegations."""
    delegations = await list_delegations(db, tenant_id)
    return ApprovalDelegationListResponse(
        items=[ApprovalDelegationResponse.model_validate(d) for d in delegations]
    )


@router.post(
    "/delegations",
    response_model=ApprovalDelegationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_new_delegation(
    body: ApprovalDelegationCreate, db: DbSession, tenant_id: TenantId, actor_id: ActorId
):
    """Create an approval delegation."""
    try:
        delegation = await create_delegation(
            db,
            tenant_id,
            actor_id,
            delegator_id=body.delegator_id,
            delegate_id=body.delegate_id,
            start_date=body.start_date,
            end_date=body.end_date,
        )
        await db.commit()
        await db.refresh(delegation)
        return ApprovalDelegationResponse.model_validate(delegation)
    except ApprovalDelegationError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
