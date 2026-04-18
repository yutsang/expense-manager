"""Multi-entity consolidation service — group management and consolidated reports.

Provides CRUD for entity groups and members, plus consolidated P&L and
balance sheet aggregation across member tenants.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.infra.models import (
    EntityGroup,
    EntityGroupMember,
    Tenant,
)

log = get_logger(__name__)


class EntityGroupNotFoundError(ValueError):
    pass


class DuplicateMemberError(ValueError):
    pass


# ── CRUD: Entity Groups ─────────────────────────────────────────────────────


async def create_group(
    db: AsyncSession,
    *,
    parent_tenant_id: str,
    name: str,
    actor_id: str | None = None,
) -> EntityGroup:
    """Create a new entity group owned by parent_tenant_id."""
    group = EntityGroup(
        id=str(uuid.uuid4()),
        parent_tenant_id=parent_tenant_id,
        name=name,
        created_by=actor_id,
        updated_by=actor_id,
    )
    db.add(group)
    await db.flush()
    return group


async def list_groups(
    db: AsyncSession,
    *,
    parent_tenant_id: str,
) -> list[EntityGroup]:
    """List all entity groups owned by parent_tenant_id."""
    result = await db.execute(
        select(EntityGroup)
        .where(EntityGroup.parent_tenant_id == parent_tenant_id)
        .order_by(EntityGroup.name)
    )
    return list(result.scalars().all())


async def get_group(
    db: AsyncSession,
    *,
    group_id: str,
    parent_tenant_id: str,
) -> EntityGroup:
    """Retrieve a single entity group, scoped to parent tenant."""
    result = await db.execute(
        select(EntityGroup).where(
            EntityGroup.id == group_id,
            EntityGroup.parent_tenant_id == parent_tenant_id,
        )
    )
    group = result.scalar_one_or_none()
    if group is None:
        raise EntityGroupNotFoundError(f"Entity group {group_id} not found")
    return group


async def delete_group(
    db: AsyncSession,
    *,
    group_id: str,
    parent_tenant_id: str,
) -> None:
    """Delete an entity group and its members (CASCADE)."""
    group = await get_group(db, group_id=group_id, parent_tenant_id=parent_tenant_id)
    await db.execute(delete(EntityGroup).where(EntityGroup.id == group.id))
    await db.flush()


# ── CRUD: Entity Group Members ──────────────────────────────────────────────


async def add_member(
    db: AsyncSession,
    *,
    group_id: str,
    parent_tenant_id: str,
    member_tenant_id: str,
    ownership_pct: Decimal = Decimal("100"),
    actor_id: str | None = None,
) -> EntityGroupMember:
    """Add a tenant as a member of an entity group."""
    # Verify the group exists and belongs to the parent
    await get_group(db, group_id=group_id, parent_tenant_id=parent_tenant_id)

    # Check for duplicate
    existing = await db.execute(
        select(EntityGroupMember).where(
            EntityGroupMember.group_id == group_id,
            EntityGroupMember.member_tenant_id == member_tenant_id,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise DuplicateMemberError(
            f"Tenant {member_tenant_id} is already a member of group {group_id}"
        )

    member = EntityGroupMember(
        id=str(uuid.uuid4()),
        group_id=group_id,
        member_tenant_id=member_tenant_id,
        ownership_pct=ownership_pct,
        created_by=actor_id,
        updated_by=actor_id,
    )
    db.add(member)
    await db.flush()
    return member


async def list_members(
    db: AsyncSession,
    *,
    group_id: str,
    parent_tenant_id: str,
) -> list[EntityGroupMember]:
    """List all members of an entity group."""
    await get_group(db, group_id=group_id, parent_tenant_id=parent_tenant_id)
    result = await db.execute(
        select(EntityGroupMember)
        .where(EntityGroupMember.group_id == group_id)
        .order_by(EntityGroupMember.created_at)
    )
    return list(result.scalars().all())


async def remove_member(
    db: AsyncSession,
    *,
    group_id: str,
    parent_tenant_id: str,
    member_id: str,
) -> None:
    """Remove a member from an entity group."""
    await get_group(db, group_id=group_id, parent_tenant_id=parent_tenant_id)
    await db.execute(
        delete(EntityGroupMember).where(EntityGroupMember.id == member_id)
    )
    await db.flush()


# ── Consolidated Reports ─────────────────────────────────────────────────────


@dataclass
class ConsolidatedPLLine:
    account_code: str
    account_name: str
    account_type: str  # revenue or expense
    subtype: str
    per_entity: dict[str, Decimal] = field(default_factory=dict)  # tenant_id -> balance
    total: Decimal = Decimal("0")


@dataclass
class ConsolidatedPL:
    from_date: date
    to_date: date
    group_id: str
    group_name: str
    revenue_lines: list[ConsolidatedPLLine]
    expense_lines: list[ConsolidatedPLLine]
    total_revenue: Decimal
    total_expenses: Decimal
    net_profit: Decimal
    member_names: dict[str, str]  # tenant_id -> tenant_name
    generated_at: datetime


@dataclass
class ConsolidatedBSLine:
    account_code: str
    account_name: str
    account_type: str
    subtype: str
    per_entity: dict[str, Decimal] = field(default_factory=dict)
    total: Decimal = Decimal("0")


@dataclass
class ConsolidatedBSSection:
    lines: list[ConsolidatedBSLine]
    total: Decimal = Decimal("0")


@dataclass
class ConsolidatedBS:
    as_of: date
    group_id: str
    group_name: str
    assets: ConsolidatedBSSection
    liabilities: ConsolidatedBSSection
    equity: ConsolidatedBSSection
    total_liabilities_and_equity: Decimal
    is_balanced: bool
    member_names: dict[str, str]
    generated_at: datetime


async def _get_member_info(
    db: AsyncSession,
    group_id: str,
    parent_tenant_id: str,
) -> tuple[EntityGroup, list[tuple[str, Decimal, str]]]:
    """Return group and list of (member_tenant_id, ownership_pct, tenant_name)."""
    group = await get_group(db, group_id=group_id, parent_tenant_id=parent_tenant_id)
    members = await list_members(db, group_id=group_id, parent_tenant_id=parent_tenant_id)

    member_ids = [m.member_tenant_id for m in members]
    if not member_ids:
        return group, []

    tenants_result = await db.execute(
        select(Tenant).where(Tenant.id.in_(member_ids))
    )
    tenant_map = {t.id: t.name for t in tenants_result.scalars().all()}

    info = [
        (m.member_tenant_id, Decimal(str(m.ownership_pct)), tenant_map.get(m.member_tenant_id, "?"))
        for m in members
    ]
    return group, info


async def get_consolidated_pnl(
    db: AsyncSession,
    *,
    group_id: str,
    parent_tenant_id: str,
    from_date: date,
    to_date: date,
) -> ConsolidatedPL:
    """Build consolidated P&L across all member tenants of a group."""
    group, member_info = await _get_member_info(db, group_id, parent_tenant_id)
    member_names = {tid: name for tid, _, name in member_info}

    # Keyed by account_code -> ConsolidatedPLLine
    lines_by_code: dict[str, ConsolidatedPLLine] = {}

    for tenant_id, ownership_pct, _ in member_info:
        pct_factor = ownership_pct / Decimal("100")

        rows = await db.execute(
            text("""
                SELECT
                    a.code,
                    a.name,
                    a.type,
                    a.subtype,
                    COALESCE(SUM(jl.credit - jl.debit), 0) AS net_credit,
                    COALESCE(SUM(jl.debit - jl.credit), 0) AS net_debit
                FROM journal_lines jl
                JOIN accounts a ON a.id = jl.account_id
                JOIN journal_entries je ON je.id = jl.journal_entry_id
                WHERE a.type IN ('revenue', 'expense')
                  AND je.status = 'posted'
                  AND jl.tenant_id = :tenant_id
                  AND je.date >= :from_date
                  AND je.date <= :to_date
                GROUP BY a.code, a.name, a.type, a.subtype
                ORDER BY a.type, a.code
            """),
            {"tenant_id": tenant_id, "from_date": from_date, "to_date": to_date},
        )
        result = rows.fetchall()

        for row in result:
            code = row.code
            if code not in lines_by_code:
                lines_by_code[code] = ConsolidatedPLLine(
                    account_code=code,
                    account_name=row.name,
                    account_type=row.type,
                    subtype=row.subtype,
                )
            line = lines_by_code[code]

            if row.type == "revenue":
                balance = Decimal(str(row.net_credit)) * pct_factor
            else:
                balance = Decimal(str(row.net_debit)) * pct_factor

            line.per_entity[tenant_id] = balance
            line.total += balance

    revenue_lines = [ln for ln in lines_by_code.values() if ln.account_type == "revenue"]
    expense_lines = [ln for ln in lines_by_code.values() if ln.account_type == "expense"]
    revenue_lines.sort(key=lambda ln: ln.account_code)
    expense_lines.sort(key=lambda ln: ln.account_code)

    total_revenue = sum(ln.total for ln in revenue_lines)
    total_expenses = sum(ln.total for ln in expense_lines)

    return ConsolidatedPL(
        from_date=from_date,
        to_date=to_date,
        group_id=group_id,
        group_name=group.name,
        revenue_lines=revenue_lines,
        expense_lines=expense_lines,
        total_revenue=total_revenue,
        total_expenses=total_expenses,
        net_profit=total_revenue - total_expenses,
        member_names=member_names,
        generated_at=datetime.now(tz=UTC),
    )


async def get_consolidated_bs(
    db: AsyncSession,
    *,
    group_id: str,
    parent_tenant_id: str,
    as_of: date,
) -> ConsolidatedBS:
    """Build consolidated balance sheet across all member tenants of a group."""
    group, member_info = await _get_member_info(db, group_id, parent_tenant_id)
    member_names = {tid: name for tid, _, name in member_info}

    lines_by_code: dict[str, ConsolidatedBSLine] = {}

    for tenant_id, ownership_pct, _ in member_info:
        pct_factor = ownership_pct / Decimal("100")

        rows = await db.execute(
            text("""
                SELECT
                    a.code,
                    a.name,
                    a.type,
                    a.subtype,
                    COALESCE(SUM(jl.functional_debit), 0) AS total_debit,
                    COALESCE(SUM(jl.functional_credit), 0) AS total_credit
                FROM journal_lines jl
                JOIN journal_entries je ON je.id = jl.journal_entry_id
                JOIN accounts a ON a.id = jl.account_id
                WHERE a.type IN ('asset', 'liability', 'equity')
                  AND je.status = 'posted'
                  AND jl.tenant_id = :tenant_id
                  AND je.date <= :as_of
                GROUP BY a.code, a.name, a.type, a.subtype
                ORDER BY a.type, a.code
            """),
            {"tenant_id": tenant_id, "as_of": as_of},
        )
        result = rows.fetchall()

        for row in result:
            code = row.code
            if code not in lines_by_code:
                lines_by_code[code] = ConsolidatedBSLine(
                    account_code=code,
                    account_name=row.name,
                    account_type=row.type,
                    subtype=row.subtype,
                )
            line = lines_by_code[code]
            td = Decimal(str(row.total_debit))
            tc = Decimal(str(row.total_credit))

            balance = (td - tc) * pct_factor if row.type == "asset" else (tc - td) * pct_factor

            line.per_entity[tenant_id] = balance
            line.total += balance

    asset_lines = [ln for ln in lines_by_code.values() if ln.account_type == "asset"]
    liability_lines = [ln for ln in lines_by_code.values() if ln.account_type == "liability"]
    equity_lines = [ln for ln in lines_by_code.values() if ln.account_type == "equity"]
    asset_lines.sort(key=lambda ln: ln.account_code)
    liability_lines.sort(key=lambda ln: ln.account_code)
    equity_lines.sort(key=lambda ln: ln.account_code)

    total_assets = sum(ln.total for ln in asset_lines)
    total_liabilities = sum(ln.total for ln in liability_lines)
    total_equity = sum(ln.total for ln in equity_lines)
    total_le = total_liabilities + total_equity

    return ConsolidatedBS(
        as_of=as_of,
        group_id=group_id,
        group_name=group.name,
        assets=ConsolidatedBSSection(lines=asset_lines, total=total_assets),
        liabilities=ConsolidatedBSSection(lines=liability_lines, total=total_liabilities),
        equity=ConsolidatedBSSection(lines=equity_lines, total=total_equity),
        total_liabilities_and_equity=total_le,
        is_balanced=abs(total_assets - total_le) < Decimal("0.01"),
        member_names=member_names,
        generated_at=datetime.now(tz=UTC),
    )
