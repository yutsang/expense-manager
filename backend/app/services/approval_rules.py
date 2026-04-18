"""Approval rules service — configurable approval workflow engine (Issue #61).

Provides rule CRUD, rule evaluation against entity values, and delegation
management. The evaluate_rules() function is called by existing approval
logic in invoices, bills, and journals to check configurable rules alongside
legacy threshold behaviour.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.emitter import emit
from app.core.logging import get_logger
from app.infra.models import ApprovalDelegation, ApprovalRule

log = get_logger(__name__)


class ApprovalRuleNotFoundError(ValueError):
    pass


class ApprovalDelegationError(ValueError):
    pass


# ---------------------------------------------------------------------------
# Rule CRUD
# ---------------------------------------------------------------------------


async def list_rules(
    db: AsyncSession,
    tenant_id: str,
    *,
    entity_type: str | None = None,
    include_inactive: bool = False,
) -> list[ApprovalRule]:
    """List approval rules for a tenant, optionally filtered by entity_type."""
    q = select(ApprovalRule).where(ApprovalRule.tenant_id == tenant_id)
    if entity_type:
        q = q.where(ApprovalRule.entity_type == entity_type)
    if not include_inactive:
        q = q.where(ApprovalRule.is_active.is_(True))
    q = q.order_by(ApprovalRule.entity_type, ApprovalRule.approval_order)
    result = await db.execute(q)
    return list(result.scalars())


async def get_rule(db: AsyncSession, tenant_id: str, rule_id: str) -> ApprovalRule:
    """Get a single approval rule by ID."""
    rule = await db.scalar(
        select(ApprovalRule).where(ApprovalRule.id == rule_id, ApprovalRule.tenant_id == tenant_id)
    )
    if not rule:
        raise ApprovalRuleNotFoundError(rule_id)
    return rule


async def create_rule(
    db: AsyncSession,
    tenant_id: str,
    actor_id: str | None,
    *,
    entity_type: str,
    condition_field: str,
    condition_operator: str,
    condition_value: str,
    required_role: str,
    approval_order: int = 1,
    description: str | None = None,
) -> ApprovalRule:
    """Create a new approval rule."""
    rule = ApprovalRule(
        tenant_id=tenant_id,
        entity_type=entity_type,
        condition_field=condition_field,
        condition_operator=condition_operator,
        condition_value=Decimal(condition_value),
        required_role=required_role,
        approval_order=approval_order,
        description=description,
        created_by=actor_id,
        updated_by=actor_id,
    )
    db.add(rule)
    await db.flush()
    await db.refresh(rule)

    await emit(
        db,
        action="approval_rule.created",
        entity_type="approval_rule",
        entity_id=rule.id,
        actor_type="user",
        actor_id=actor_id,
        tenant_id=tenant_id,
        after={
            "entity_type": entity_type,
            "condition_field": condition_field,
            "condition_operator": condition_operator,
            "condition_value": condition_value,
            "required_role": required_role,
            "approval_order": approval_order,
        },
    )
    log.info("approval_rule.created", tenant_id=tenant_id, rule_id=rule.id)
    return rule


async def update_rule(
    db: AsyncSession,
    tenant_id: str,
    actor_id: str | None,
    rule_id: str,
    *,
    entity_type: str | None = None,
    condition_field: str | None = None,
    condition_operator: str | None = None,
    condition_value: str | None = None,
    required_role: str | None = None,
    approval_order: int | None = None,
    description: str | None = None,
    is_active: bool | None = None,
) -> ApprovalRule:
    """Update an existing approval rule."""
    rule = await get_rule(db, tenant_id, rule_id)
    before: dict[str, object] = {}
    after: dict[str, object] = {}

    if entity_type is not None and entity_type != rule.entity_type:
        before["entity_type"] = rule.entity_type
        rule.entity_type = entity_type
        after["entity_type"] = entity_type
    if condition_field is not None and condition_field != rule.condition_field:
        before["condition_field"] = rule.condition_field
        rule.condition_field = condition_field
        after["condition_field"] = condition_field
    if condition_operator is not None and condition_operator != rule.condition_operator:
        before["condition_operator"] = rule.condition_operator
        rule.condition_operator = condition_operator
        after["condition_operator"] = condition_operator
    if condition_value is not None:
        new_val = Decimal(condition_value)
        before["condition_value"] = str(rule.condition_value)
        rule.condition_value = new_val
        after["condition_value"] = condition_value
    if required_role is not None and required_role != rule.required_role:
        before["required_role"] = rule.required_role
        rule.required_role = required_role
        after["required_role"] = required_role
    if approval_order is not None and approval_order != rule.approval_order:
        before["approval_order"] = rule.approval_order
        rule.approval_order = approval_order
        after["approval_order"] = approval_order
    if description is not None:
        before["description"] = rule.description
        rule.description = description
        after["description"] = description
    if is_active is not None and is_active != rule.is_active:
        before["is_active"] = rule.is_active
        rule.is_active = is_active
        after["is_active"] = is_active

    rule.updated_by = actor_id
    rule.updated_at = datetime.now(tz=UTC)
    rule.version += 1
    await db.flush()
    await db.refresh(rule)

    if after:
        await emit(
            db,
            action="approval_rule.updated",
            entity_type="approval_rule",
            entity_id=rule_id,
            actor_type="user",
            actor_id=actor_id,
            tenant_id=tenant_id,
            before=before,
            after=after,
        )
    log.info("approval_rule.updated", tenant_id=tenant_id, rule_id=rule_id)
    return rule


async def delete_rule(
    db: AsyncSession, tenant_id: str, actor_id: str | None, rule_id: str
) -> ApprovalRule:
    """Soft-delete an approval rule by setting is_active=False."""
    rule = await get_rule(db, tenant_id, rule_id)
    rule.is_active = False
    rule.updated_by = actor_id
    rule.updated_at = datetime.now(tz=UTC)
    rule.version += 1
    await db.flush()
    await db.refresh(rule)

    await emit(
        db,
        action="approval_rule.deactivated",
        entity_type="approval_rule",
        entity_id=rule_id,
        actor_type="user",
        actor_id=actor_id,
        tenant_id=tenant_id,
        before={"is_active": True},
        after={"is_active": False},
    )
    log.info("approval_rule.deactivated", tenant_id=tenant_id, rule_id=rule_id)
    return rule


# ---------------------------------------------------------------------------
# Rule evaluation
# ---------------------------------------------------------------------------

_OPERATORS = {
    "gte": lambda val, threshold: val >= threshold,
    "lte": lambda val, threshold: val <= threshold,
    "gt": lambda val, threshold: val > threshold,
    "lt": lambda val, threshold: val < threshold,
    "eq": lambda val, threshold: val == threshold,
}


async def evaluate_rules(
    db: AsyncSession,
    tenant_id: str,
    entity_type: str,
    entity_value: Decimal,
) -> list[ApprovalRule]:
    """Evaluate active rules for an entity type against a value.

    Returns the list of matching rules (those whose conditions are satisfied),
    sorted by approval_order. Each matching rule indicates a required approver
    role and order.
    """
    rules = await list_rules(db, tenant_id, entity_type=entity_type)
    matched: list[ApprovalRule] = []
    for rule in rules:
        op_fn = _OPERATORS.get(rule.condition_operator)
        if op_fn is None:
            continue
        threshold = Decimal(str(rule.condition_value))
        if op_fn(entity_value, threshold):
            matched.append(rule)

    # Sort by approval_order for deterministic ordering
    matched.sort(key=lambda r: r.approval_order)
    return matched


# ---------------------------------------------------------------------------
# Delegation
# ---------------------------------------------------------------------------


async def create_delegation(
    db: AsyncSession,
    tenant_id: str,
    actor_id: str | None,
    *,
    delegator_id: str,
    delegate_id: str,
    start_date: date,
    end_date: date,
) -> ApprovalDelegation:
    """Create an approval delegation from one user to another."""
    if delegator_id == delegate_id:
        raise ApprovalDelegationError("Cannot delegate to yourself")
    if end_date < start_date:
        raise ApprovalDelegationError("end_date must be on or after start_date")

    delegation = ApprovalDelegation(
        tenant_id=tenant_id,
        delegator_id=delegator_id,
        delegate_id=delegate_id,
        start_date=start_date,
        end_date=end_date,
        created_by=actor_id,
        updated_by=actor_id,
    )
    db.add(delegation)
    await db.flush()
    await db.refresh(delegation)

    await emit(
        db,
        action="approval_delegation.created",
        entity_type="approval_delegation",
        entity_id=delegation.id,
        actor_type="user",
        actor_id=actor_id,
        tenant_id=tenant_id,
        after={
            "delegator_id": delegator_id,
            "delegate_id": delegate_id,
            "start_date": str(start_date),
            "end_date": str(end_date),
        },
    )
    log.info(
        "approval_delegation.created",
        tenant_id=tenant_id,
        delegation_id=delegation.id,
    )
    return delegation


async def list_delegations(
    db: AsyncSession,
    tenant_id: str,
    *,
    active_only: bool = True,
) -> list[ApprovalDelegation]:
    """List approval delegations for a tenant."""
    q = select(ApprovalDelegation).where(ApprovalDelegation.tenant_id == tenant_id)
    if active_only:
        q = q.where(ApprovalDelegation.is_active.is_(True))
    q = q.order_by(ApprovalDelegation.start_date)
    result = await db.execute(q)
    return list(result.scalars())


async def get_effective_approver(
    db: AsyncSession,
    tenant_id: str,
    original_approver_id: str,
    *,
    on_date: date | None = None,
) -> str:
    """Return the effective approver, checking for active delegations.

    If the original approver has delegated their authority to someone else
    for the given date, the delegate's ID is returned. Otherwise, the
    original approver is returned.
    """
    check_date = on_date or date.today()
    delegation = await db.scalar(
        select(ApprovalDelegation).where(
            ApprovalDelegation.tenant_id == tenant_id,
            ApprovalDelegation.delegator_id == original_approver_id,
            ApprovalDelegation.is_active.is_(True),
            ApprovalDelegation.start_date <= check_date,
            ApprovalDelegation.end_date >= check_date,
        )
    )
    if delegation:
        return delegation.delegate_id
    return original_approver_id
