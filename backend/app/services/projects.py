"""Project & time tracking service — CRUD, billing rate resolution, invoice generation.

Supports professional services workflows: track time, resolve billing rates,
and generate invoices from approved unbilled time entries.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_EVEN, Decimal

from sqlalchemy import and_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.emitter import emit
from app.core.logging import get_logger
from app.infra.models import (
    BillingRate,
    Contact,
    Invoice,
    InvoiceLine,
    Project,
    TimeEntry,
)

log = get_logger(__name__)

_QUANTIZE_4 = Decimal("0.0001")


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class ProjectNotFoundError(ValueError):
    pass


class TimeEntryNotFoundError(ValueError):
    pass


class TimeEntryLockedError(ValueError):
    """Raised when attempting to modify a billed time entry."""

    pass


class NoUnbilledEntriesError(ValueError):
    pass


class NoBillingRateError(ValueError):
    """Raised when no applicable billing rate is found for a time entry."""

    pass


# ---------------------------------------------------------------------------
# Project CRUD
# ---------------------------------------------------------------------------


async def create_project(
    db: AsyncSession,
    tenant_id: str,
    actor_id: str | None,
    *,
    contact_id: str,
    name: str,
    code: str | None = None,
    description: str | None = None,
    status: str = "active",
    budget_hours: Decimal | None = None,
    budget_amount: Decimal | None = None,
    currency: str = "USD",
) -> Project:
    # Validate contact exists for this tenant
    contact = await db.scalar(
        select(Contact).where(Contact.id == contact_id, Contact.tenant_id == tenant_id)
    )
    if not contact:
        raise ValueError(f"Contact not found: {contact_id}")

    proj = Project(
        tenant_id=tenant_id,
        contact_id=contact_id,
        name=name,
        code=code,
        description=description,
        status=status,
        budget_hours=budget_hours,
        budget_amount=budget_amount,
        currency=currency,
        created_by=actor_id,
        updated_by=actor_id,
    )
    db.add(proj)
    await db.flush()
    await db.refresh(proj)

    await emit(
        db,
        action="project.created",
        entity_type="project",
        entity_id=proj.id,
        actor_type="user",
        actor_id=actor_id,
        tenant_id=tenant_id,
        after={"name": proj.name, "code": proj.code, "status": proj.status},
    )
    log.info("project.created", tenant_id=tenant_id, project_id=proj.id)
    return proj


async def list_projects(
    db: AsyncSession,
    tenant_id: str,
    *,
    status: str | None = None,
    contact_id: str | None = None,
    limit: int = 50,
    cursor: str | None = None,
) -> list[Project]:
    q = select(Project).where(Project.tenant_id == tenant_id)
    if status:
        q = q.where(Project.status == status)
    if contact_id:
        q = q.where(Project.contact_id == contact_id)
    if cursor:
        q = q.where(Project.id > cursor)
    q = q.order_by(Project.created_at.desc(), Project.id).limit(limit)
    result = await db.execute(q)
    return list(result.scalars())


async def get_project(db: AsyncSession, tenant_id: str, project_id: str) -> Project:
    proj = await db.scalar(
        select(Project).where(Project.id == project_id, Project.tenant_id == tenant_id)
    )
    if not proj:
        raise ProjectNotFoundError(project_id)
    return proj


async def update_project(
    db: AsyncSession,
    tenant_id: str,
    project_id: str,
    actor_id: str | None,
    *,
    name: str | None = None,
    code: str | None = None,
    description: str | None = None,
    status: str | None = None,
    budget_hours: Decimal | None = None,
    budget_amount: Decimal | None = None,
    currency: str | None = None,
) -> Project:
    proj = await get_project(db, tenant_id, project_id)
    before: dict = {}
    after: dict = {}

    for field, value in [
        ("name", name),
        ("code", code),
        ("description", description),
        ("status", status),
        ("budget_hours", budget_hours),
        ("budget_amount", budget_amount),
        ("currency", currency),
    ]:
        if value is not None:
            before[field] = str(getattr(proj, field))
            setattr(proj, field, value)
            after[field] = str(value)

    if after:
        proj.updated_by = actor_id
        proj.version += 1
        await db.flush()
        await db.refresh(proj)

        await emit(
            db,
            action="project.updated",
            entity_type="project",
            entity_id=proj.id,
            actor_type="user",
            actor_id=actor_id,
            tenant_id=tenant_id,
            before=before,
            after=after,
        )
        log.info("project.updated", tenant_id=tenant_id, project_id=proj.id)

    return proj


# ---------------------------------------------------------------------------
# Time Entry CRUD
# ---------------------------------------------------------------------------


async def create_time_entry(
    db: AsyncSession,
    tenant_id: str,
    actor_id: str | None,
    *,
    project_id: str,
    user_id: str,
    entry_date: date,
    hours: Decimal,
    description: str | None = None,
    is_billable: bool = True,
) -> TimeEntry:
    # Validate project exists
    await get_project(db, tenant_id, project_id)

    te = TimeEntry(
        tenant_id=tenant_id,
        project_id=project_id,
        user_id=user_id,
        entry_date=entry_date,
        hours=hours,
        description=description,
        is_billable=is_billable,
        created_by=actor_id,
        updated_by=actor_id,
    )
    db.add(te)
    await db.flush()
    await db.refresh(te)

    await emit(
        db,
        action="time_entry.created",
        entity_type="time_entry",
        entity_id=te.id,
        actor_type="user",
        actor_id=actor_id,
        tenant_id=tenant_id,
        after={
            "project_id": project_id,
            "hours": str(hours),
            "entry_date": str(entry_date),
        },
    )
    log.info("time_entry.created", tenant_id=tenant_id, time_entry_id=te.id)
    return te


async def list_time_entries(
    db: AsyncSession,
    tenant_id: str,
    *,
    project_id: str | None = None,
    user_id: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    is_billable: bool | None = None,
    approval_status: str | None = None,
    limit: int = 50,
    cursor: str | None = None,
) -> list[TimeEntry]:
    q = select(TimeEntry).where(TimeEntry.tenant_id == tenant_id)
    if project_id:
        q = q.where(TimeEntry.project_id == project_id)
    if user_id:
        q = q.where(TimeEntry.user_id == user_id)
    if from_date:
        q = q.where(TimeEntry.entry_date >= from_date)
    if to_date:
        q = q.where(TimeEntry.entry_date <= to_date)
    if is_billable is not None:
        q = q.where(TimeEntry.is_billable == is_billable)
    if approval_status:
        q = q.where(TimeEntry.approval_status == approval_status)
    if cursor:
        q = q.where(TimeEntry.id > cursor)
    q = q.order_by(TimeEntry.entry_date.desc(), TimeEntry.id).limit(limit)
    result = await db.execute(q)
    return list(result.scalars())


async def get_time_entry(db: AsyncSession, tenant_id: str, entry_id: str) -> TimeEntry:
    te = await db.scalar(
        select(TimeEntry).where(TimeEntry.id == entry_id, TimeEntry.tenant_id == tenant_id)
    )
    if not te:
        raise TimeEntryNotFoundError(entry_id)
    return te


async def update_time_entry(
    db: AsyncSession,
    tenant_id: str,
    entry_id: str,
    actor_id: str | None,
    *,
    hours: Decimal | None = None,
    description: str | None = None,
    is_billable: bool | None = None,
    approval_status: str | None = None,
    entry_date: date | None = None,
) -> TimeEntry:
    te = await get_time_entry(db, tenant_id, entry_id)

    if te.billed_invoice_id is not None:
        raise TimeEntryLockedError(
            f"Time entry {entry_id} is billed (invoice {te.billed_invoice_id}) and cannot be modified"
        )

    before: dict = {}
    after: dict = {}

    for field, value in [
        ("hours", hours),
        ("description", description),
        ("is_billable", is_billable),
        ("approval_status", approval_status),
        ("entry_date", entry_date),
    ]:
        if value is not None:
            before[field] = str(getattr(te, field))
            setattr(te, field, value)
            after[field] = str(value)

    if after:
        te.updated_by = actor_id
        te.version += 1
        await db.flush()
        await db.refresh(te)

        await emit(
            db,
            action="time_entry.updated",
            entity_type="time_entry",
            entity_id=te.id,
            actor_type="user",
            actor_id=actor_id,
            tenant_id=tenant_id,
            before=before,
            after=after,
        )
        log.info("time_entry.updated", tenant_id=tenant_id, time_entry_id=te.id)

    return te


# ---------------------------------------------------------------------------
# Billing Rate CRUD
# ---------------------------------------------------------------------------


async def create_billing_rate(
    db: AsyncSession,
    tenant_id: str,
    actor_id: str | None,
    *,
    rate: Decimal,
    effective_from: date,
    effective_to: date | None = None,
    project_id: str | None = None,
    user_id: str | None = None,
    role: str | None = None,
    currency: str = "USD",
) -> BillingRate:
    br = BillingRate(
        tenant_id=tenant_id,
        project_id=project_id,
        user_id=user_id,
        role=role,
        rate=rate,
        currency=currency,
        effective_from=effective_from,
        effective_to=effective_to,
        created_by=actor_id,
        updated_by=actor_id,
    )
    db.add(br)
    await db.flush()
    await db.refresh(br)

    await emit(
        db,
        action="billing_rate.created",
        entity_type="billing_rate",
        entity_id=br.id,
        actor_type="user",
        actor_id=actor_id,
        tenant_id=tenant_id,
        after={"rate": str(rate), "project_id": project_id, "user_id": user_id, "role": role},
    )
    log.info("billing_rate.created", tenant_id=tenant_id, billing_rate_id=br.id)
    return br


async def list_billing_rates(
    db: AsyncSession,
    tenant_id: str,
    *,
    project_id: str | None = None,
    limit: int = 50,
    cursor: str | None = None,
) -> list[BillingRate]:
    q = select(BillingRate).where(BillingRate.tenant_id == tenant_id)
    if project_id:
        q = q.where(BillingRate.project_id == project_id)
    if cursor:
        q = q.where(BillingRate.id > cursor)
    q = q.order_by(BillingRate.effective_from.desc(), BillingRate.id).limit(limit)
    result = await db.execute(q)
    return list(result.scalars())


# ---------------------------------------------------------------------------
# Rate resolution
# ---------------------------------------------------------------------------


async def resolve_billing_rate(
    db: AsyncSession,
    tenant_id: str,
    *,
    project_id: str,
    user_id: str,
    entry_date: date,
) -> Decimal:
    """Resolve the applicable billing rate for a time entry.

    Priority order:
      1. Project-specific + user-specific rate
      2. User-specific rate (any project)
      3. Role-level rate for the project (not implemented yet -- needs user->role mapping)
      4. Tenant-default rate (no project, no user)

    All rates must be effective on entry_date (effective_from <= date, effective_to is null or >= date).
    """
    date_filter = and_(
        BillingRate.effective_from <= entry_date,
        (BillingRate.effective_to >= entry_date) | (BillingRate.effective_to.is_(None)),
    )

    # 1. Project + user specific
    rate = await db.scalar(
        select(BillingRate.rate).where(
            BillingRate.tenant_id == tenant_id,
            BillingRate.project_id == project_id,
            BillingRate.user_id == user_id,
            date_filter,
        ).order_by(BillingRate.effective_from.desc()).limit(1)
    )
    if rate is not None:
        return Decimal(str(rate))

    # 2. User-specific (any project)
    rate = await db.scalar(
        select(BillingRate.rate).where(
            BillingRate.tenant_id == tenant_id,
            BillingRate.project_id.is_(None),
            BillingRate.user_id == user_id,
            date_filter,
        ).order_by(BillingRate.effective_from.desc()).limit(1)
    )
    if rate is not None:
        return Decimal(str(rate))

    # 3. Project-level role rate (no specific user)
    rate = await db.scalar(
        select(BillingRate.rate).where(
            BillingRate.tenant_id == tenant_id,
            BillingRate.project_id == project_id,
            BillingRate.user_id.is_(None),
            date_filter,
        ).order_by(BillingRate.effective_from.desc()).limit(1)
    )
    if rate is not None:
        return Decimal(str(rate))

    # 4. Tenant default (no project, no user)
    rate = await db.scalar(
        select(BillingRate.rate).where(
            BillingRate.tenant_id == tenant_id,
            BillingRate.project_id.is_(None),
            BillingRate.user_id.is_(None),
            date_filter,
        ).order_by(BillingRate.effective_from.desc()).limit(1)
    )
    if rate is not None:
        return Decimal(str(rate))

    raise NoBillingRateError(
        f"No billing rate found for project={project_id}, user={user_id}, date={entry_date}"
    )


# ---------------------------------------------------------------------------
# WIP (Work In Progress) summary
# ---------------------------------------------------------------------------


async def get_wip(
    db: AsyncSession,
    tenant_id: str,
    project_id: str,
) -> dict:
    """Return unbilled time entries with total WIP value.

    Returns dict with keys: entries, total_hours, total_amount, currency.
    """
    await get_project(db, tenant_id, project_id)

    result = await db.execute(
        select(TimeEntry).where(
            TimeEntry.tenant_id == tenant_id,
            TimeEntry.project_id == project_id,
            TimeEntry.is_billable.is_(True),
            TimeEntry.approval_status == "approved",
            TimeEntry.billed_invoice_id.is_(None),
        ).order_by(TimeEntry.entry_date)
    )
    entries = list(result.scalars())

    total_hours = Decimal("0")
    total_amount = Decimal("0")
    entry_details: list[dict] = []

    for entry in entries:
        hours = Decimal(str(entry.hours))
        total_hours += hours
        try:
            rate = await resolve_billing_rate(
                db,
                tenant_id,
                project_id=project_id,
                user_id=entry.user_id,
                entry_date=entry.entry_date,
            )
            amount = (hours * rate).quantize(_QUANTIZE_4, ROUND_HALF_EVEN)
        except NoBillingRateError:
            rate = Decimal("0")
            amount = Decimal("0")

        total_amount += amount
        entry_details.append({
            "id": entry.id,
            "entry_date": str(entry.entry_date),
            "user_id": entry.user_id,
            "hours": str(hours),
            "rate": str(rate),
            "amount": str(amount),
            "description": entry.description,
        })

    proj = await get_project(db, tenant_id, project_id)
    return {
        "project_id": project_id,
        "entries": entry_details,
        "total_hours": str(total_hours),
        "total_amount": str(total_amount),
        "currency": proj.currency,
    }


# ---------------------------------------------------------------------------
# Invoice generation from time entries
# ---------------------------------------------------------------------------


async def generate_invoice(
    db: AsyncSession,
    tenant_id: str,
    actor_id: str | None,
    project_id: str,
    from_date: date,
    to_date: date,
) -> Invoice:
    """Generate a draft invoice from unbilled, approved time entries in date range.

    Steps:
      1. Query unbilled, approved, billable time entries for the project in date range.
      2. For each entry, resolve the billing rate.
      3. Create a draft invoice with line items.
      4. Mark entries as billed (set billed_invoice_id).
      5. Return the draft invoice.
    """
    proj = await get_project(db, tenant_id, project_id)

    # Fetch unbilled, approved, billable entries in range
    result = await db.execute(
        select(TimeEntry).where(
            TimeEntry.tenant_id == tenant_id,
            TimeEntry.project_id == project_id,
            TimeEntry.is_billable.is_(True),
            TimeEntry.approval_status == "approved",
            TimeEntry.billed_invoice_id.is_(None),
            TimeEntry.entry_date >= from_date,
            TimeEntry.entry_date <= to_date,
        ).order_by(TimeEntry.entry_date)
    )
    entries = list(result.scalars())

    if not entries:
        raise NoUnbilledEntriesError(
            f"No unbilled approved time entries for project {project_id} "
            f"between {from_date} and {to_date}"
        )

    # Build invoice lines
    subtotal = Decimal("0")
    line_models: list[InvoiceLine] = []

    for i, entry in enumerate(entries, start=1):
        hours = Decimal(str(entry.hours))
        rate = await resolve_billing_rate(
            db,
            tenant_id,
            project_id=project_id,
            user_id=entry.user_id,
            entry_date=entry.entry_date,
        )
        line_amount = (hours * rate).quantize(_QUANTIZE_4, ROUND_HALF_EVEN)
        subtotal += line_amount

        desc = entry.description or f"Time entry {entry.entry_date}"
        line_models.append(
            InvoiceLine(
                tenant_id=tenant_id,
                line_no=i,
                description=f"{desc} ({hours}h @ {rate})",
                quantity=hours,
                unit_price=rate,
                line_amount=line_amount,
                tax_amount=Decimal("0"),
            )
        )

    # Create draft invoice
    inv = Invoice(
        tenant_id=tenant_id,
        number=f"DRAFT-{uuid.uuid4().hex[:8].upper()}",
        status="draft",
        contact_id=proj.contact_id,
        issue_date=datetime.now(tz=UTC).date(),
        currency=proj.currency,
        subtotal=subtotal,
        tax_total=Decimal("0"),
        total=subtotal,
        amount_due=subtotal,
        functional_total=subtotal,
        notes=f"Time billing for project {proj.name} ({from_date} to {to_date})",
        created_by=actor_id,
        updated_by=actor_id,
    )
    db.add(inv)
    await db.flush()

    # Attach lines to invoice and an account_id placeholder
    for lm in line_models:
        lm.invoice_id = inv.id
        db.add(lm)

    # Mark time entries as billed
    entry_ids = [e.id for e in entries]
    await db.execute(
        update(TimeEntry)
        .where(TimeEntry.id.in_(entry_ids))
        .values(billed_invoice_id=inv.id, updated_by=actor_id)
    )

    await db.flush()
    await db.refresh(inv)

    await emit(
        db,
        action="project.invoice_generated",
        entity_type="invoice",
        entity_id=inv.id,
        actor_type="user",
        actor_id=actor_id,
        tenant_id=tenant_id,
        after={
            "project_id": project_id,
            "entries_count": len(entries),
            "total": str(subtotal),
        },
    )
    log.info(
        "project.invoice_generated",
        tenant_id=tenant_id,
        project_id=project_id,
        invoice_id=inv.id,
        entries=len(entries),
    )
    return inv
