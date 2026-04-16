"""Period service — lifecycle management and pre-generation."""
from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.emitter import emit
from app.core.logging import get_logger
from app.domain.ledger.period import (
    PeriodStatus,
    PeriodTransitionError,
    assert_transition_allowed,
    can_post,
    generate_periods,
)
from app.infra.models import Period

log = get_logger(__name__)


class PeriodNotFoundError(ValueError):
    pass


class PeriodPostingError(ValueError):
    pass


async def get_period(db: AsyncSession, *, period_id: str, tenant_id: str) -> Period:
    result = await db.execute(
        select(Period).where(Period.id == period_id, Period.tenant_id == tenant_id)
    )
    p = result.scalar_one_or_none()
    if not p:
        raise PeriodNotFoundError(f"Period {period_id} not found")
    return p


async def get_period_for_date(
    db: AsyncSession, *, tenant_id: str, on_date: date
) -> Period:
    """Return the period that covers `on_date`. Raises if none found."""
    from sqlalchemy import func

    result = await db.execute(
        select(Period).where(
            Period.tenant_id == tenant_id,
            func.date(Period.start_date) <= on_date,
            func.date(Period.end_date) >= on_date,
        )
    )
    p = result.scalar_one_or_none()
    if not p:
        raise PeriodNotFoundError(f"No period found covering {on_date}")
    return p


async def list_periods(
    db: AsyncSession, *, tenant_id: str, status: str | None = None
) -> list[Period]:
    q = select(Period).where(Period.tenant_id == tenant_id)
    if status:
        q = q.where(Period.status == status)
    q = q.order_by(Period.start_date)
    result = await db.execute(q)
    return list(result.scalars().all())


async def assert_can_post(
    db: AsyncSession, *, period_id: str, tenant_id: str, admin_override: bool = False
) -> Period:
    """Assert that a journal can be posted into this period. Returns period."""
    period = await get_period(db, period_id=period_id, tenant_id=tenant_id)
    status = PeriodStatus(period.status)
    if not can_post(status, admin_override=admin_override):
        raise PeriodPostingError(
            f"Period '{period.name}' is {period.status} — cannot post"
        )
    return period


async def transition_period(
    db: AsyncSession,
    *,
    period_id: str,
    tenant_id: str,
    target_status: str,
    actor_id: str,
    reason: str | None = None,
    is_auditor: bool = False,
) -> Period:
    period = await get_period(db, period_id=period_id, tenant_id=tenant_id)
    current = PeriodStatus(period.status)
    target = PeriodStatus(target_status)

    # Hard_closed → audited requires auditor role (enforced in API layer too)
    if current == PeriodStatus.HARD_CLOSED and not is_auditor:
        raise PeriodTransitionError("Reopening a hard-closed period requires Auditor role")

    assert_transition_allowed(current, target)

    now = datetime.now(tz=UTC)
    before = {"status": period.status}

    period.status = target.value
    period.updated_at = now
    period.version += 1

    if target in (PeriodStatus.SOFT_CLOSED, PeriodStatus.HARD_CLOSED):
        period.closed_at = now
        period.closed_by = actor_id
        period.closed_reason = reason
    elif target == PeriodStatus.OPEN:
        period.reopened_at = now
        period.reopened_by = actor_id
        period.reopened_reason = reason

    await db.flush()

    await emit(
        db,
        action=f"period.{target.value}",
        entity_type="period",
        entity_id=period_id,
        actor_type="user",
        actor_id=actor_id,
        tenant_id=tenant_id,
        before=before,
        after={"status": target.value, "reason": reason},
    )
    log.info("period_transitioned", period=period.name, from_=current, to=target)
    return period


async def provision_periods(
    db: AsyncSession,
    *,
    tenant_id: str,
    functional_currency: str,
    fiscal_year_start_month: int,
    from_date: date | None = None,
    months: int = 24,
) -> list[Period]:
    """Generate monthly periods for the tenant (called on onboarding). Idempotent."""
    start = from_date or date.today().replace(day=1)
    period_dicts = generate_periods(
        tenant_id=tenant_id,
        functional_currency=functional_currency,
        fiscal_year_start_month=fiscal_year_start_month,
        from_date=start,
        months=months,
    )

    created = []
    for pd in period_dicts:
        # Skip if already exists
        existing = await db.execute(
            select(Period).where(
                Period.tenant_id == tenant_id, Period.name == pd["name"]
            )
        )
        if existing.scalar_one_or_none():
            continue
        period = Period(
            id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            name=pd["name"],
            start_date=datetime.combine(pd["start_date"], datetime.min.time()).replace(tzinfo=UTC),
            end_date=datetime.combine(pd["end_date"], datetime.min.time()).replace(tzinfo=UTC),
            status=PeriodStatus.OPEN.value,
            created_at=datetime.now(tz=UTC),
            updated_at=datetime.now(tz=UTC),
        )
        db.add(period)
        created.append(period)

    if created:
        await db.flush()
        log.info("periods_provisioned", count=len(created), tenant_id=tenant_id)
    return created
