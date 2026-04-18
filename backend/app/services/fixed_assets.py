"""Fixed assets service — register, depreciate (Issue #41).

Depreciation methods:
  - straight_line: (cost - residual) / useful_life_months per month
  - declining_balance: book_value * (2 / useful_life_months) per month,
    clamped so book_value never drops below residual_value
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.emitter import emit
from app.core.logging import get_logger
from app.domain.assets.depreciation import calculate_depreciation
from app.infra.models import FixedAsset, JournalEntry, JournalLine

log = get_logger(__name__)

_QUANTIZE_4 = Decimal("0.0001")

# Re-export for backward compatibility
__all__ = ["calculate_depreciation"]


async def create_asset(
    db: AsyncSession,
    tenant_id: str,
    actor_id: str | None,
    *,
    name: str,
    category: str,
    acquisition_date: str,
    cost: Decimal,
    residual_value: Decimal,
    useful_life_months: int,
    depreciation_method: str,
    asset_account_id: str,
    depreciation_account_id: str,
    accumulated_depreciation_account_id: str,
    description: str | None = None,
) -> FixedAsset:
    """Register a new fixed asset."""
    asset = FixedAsset(
        tenant_id=tenant_id,
        name=name,
        category=category,
        acquisition_date=acquisition_date,
        cost=cost,
        residual_value=residual_value,
        useful_life_months=useful_life_months,
        depreciation_method=depreciation_method,
        asset_account_id=asset_account_id,
        depreciation_account_id=depreciation_account_id,
        accumulated_depreciation_account_id=accumulated_depreciation_account_id,
        description=description,
        status="active",
        created_by=actor_id,
        updated_by=actor_id,
    )
    db.add(asset)
    await db.flush()
    await db.refresh(asset)

    await emit(
        db,
        action="asset.created",
        entity_type="fixed_asset",
        entity_id=asset.id,
        actor_type="user",
        actor_id=actor_id,
        tenant_id=tenant_id,
        after={"name": name, "cost": str(cost), "category": category},
    )
    log.info("asset.created", tenant_id=tenant_id, asset_id=asset.id)
    return asset


async def list_assets(
    db: AsyncSession,
    tenant_id: str,
    *,
    status: str | None = None,
    limit: int = 50,
    cursor: str | None = None,
) -> list[FixedAsset]:
    """List fixed assets for a tenant."""
    q = select(FixedAsset).where(FixedAsset.tenant_id == tenant_id)
    if status:
        q = q.where(FixedAsset.status == status)
    if cursor:
        q = q.where(FixedAsset.id > cursor)
    q = q.order_by(FixedAsset.acquisition_date.desc(), FixedAsset.id).limit(limit)
    result = await db.execute(q)
    return list(result.scalars())


async def get_asset(db: AsyncSession, tenant_id: str, asset_id: str) -> FixedAsset:
    """Get a single fixed asset by ID."""
    asset = await db.scalar(
        select(FixedAsset).where(FixedAsset.id == asset_id, FixedAsset.tenant_id == tenant_id)
    )
    if not asset:
        raise ValueError(f"Fixed asset not found: {asset_id}")
    return asset


async def _count_existing_depreciation_entries(
    db: AsyncSession, tenant_id: str, asset_id: str
) -> int:
    """Count how many depreciation journal entries already exist for this asset."""
    result = await db.execute(
        select(func.count())
        .select_from(JournalEntry)
        .where(
            JournalEntry.tenant_id == tenant_id,
            JournalEntry.source_type == "depreciation",
            JournalEntry.source_id == asset_id,
            JournalEntry.status == "posted",
        )
    )
    return result.scalar() or 0


async def depreciate_asset(
    db: AsyncSession,
    tenant_id: str,
    actor_id: str | None,
    *,
    asset_id: str,
    period_id: str,
) -> JournalEntry:
    """Calculate depreciation for one period and create a draft journal entry.

    Returns the created journal entry.
    """
    asset = await get_asset(db, tenant_id, asset_id)

    if asset.status != "active":
        raise ValueError(f"Cannot depreciate asset with status '{asset.status}'")

    months_elapsed = await _count_existing_depreciation_entries(db, tenant_id, asset_id)
    months_elapsed += 1  # this will be the next month

    # Parse acquisition_date for first-month pro-rating
    acq_date: date | None = None
    raw_acq = asset.acquisition_date
    if isinstance(raw_acq, date):
        acq_date = raw_acq
    elif isinstance(raw_acq, str):
        acq_date = date.fromisoformat(raw_acq)

    depr_amount = calculate_depreciation(
        cost=Decimal(str(asset.cost)),
        residual_value=Decimal(str(asset.residual_value)),
        useful_life_months=asset.useful_life_months,
        method=asset.depreciation_method,
        months_elapsed=months_elapsed,
        acquisition_date=acq_date,
    )

    if depr_amount <= Decimal("0"):
        raise ValueError("No depreciation to record — asset may be fully depreciated")

    now = datetime.now(tz=UTC)

    je = JournalEntry(
        tenant_id=tenant_id,
        number=f"JE-DEP-{asset.id[:8]}-{months_elapsed:03d}",
        date=now,
        period_id=period_id,
        status="draft",
        description=f"Depreciation — {asset.name} (month {months_elapsed})",
        source_type="depreciation",
        source_id=asset_id,
        currency="HKD",
        total_debit=depr_amount,
        total_credit=depr_amount,
        created_by=actor_id,
        updated_by=actor_id,
    )
    db.add(je)
    await db.flush()

    # Dr Depreciation Expense
    db.add(
        JournalLine(
            tenant_id=tenant_id,
            journal_entry_id=je.id,
            line_no=1,
            account_id=asset.depreciation_account_id,
            description=f"Depreciation �� {asset.name}",
            debit=depr_amount,
            credit=Decimal("0"),
            currency="HKD",
            functional_debit=depr_amount,
            functional_credit=Decimal("0"),
        )
    )

    # Cr Accumulated Depreciation
    db.add(
        JournalLine(
            tenant_id=tenant_id,
            journal_entry_id=je.id,
            line_no=2,
            account_id=asset.accumulated_depreciation_account_id,
            description=f"Accumulated depreciation — {asset.name}",
            debit=Decimal("0"),
            credit=depr_amount,
            currency="HKD",
            functional_debit=Decimal("0"),
            functional_credit=depr_amount,
        )
    )

    await db.flush()

    await emit(
        db,
        action="asset.depreciated",
        entity_type="fixed_asset",
        entity_id=asset_id,
        actor_type="user",
        actor_id=actor_id,
        tenant_id=tenant_id,
        after={
            "depreciation_amount": str(depr_amount),
            "months_elapsed": months_elapsed,
            "journal_entry_id": je.id,
        },
    )
    log.info("asset.depreciated", tenant_id=tenant_id, asset_id=asset_id, amount=str(depr_amount))
    return je
