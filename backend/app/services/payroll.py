"""Payroll service — salary records with MPF tracking (Issue #46)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.emitter import emit
from app.core.logging import get_logger
from app.domain.payroll.mpf import calculate_mpf
from app.infra.models import SalaryRecord

log = get_logger(__name__)


async def create_salary_record(
    db: AsyncSession,
    tenant_id: str,
    actor_id: str | None,
    *,
    employee_contact_id: str,
    period_id: str,
    gross_salary: Decimal,
    mpf_scheme_name: str | None = None,
    payment_date: str | None = None,
) -> SalaryRecord:
    """Create a salary record with auto-calculated MPF amounts."""
    mpf = calculate_mpf(gross_salary=gross_salary)

    record = SalaryRecord(
        tenant_id=tenant_id,
        employee_contact_id=employee_contact_id,
        period_id=period_id,
        gross_salary=gross_salary,
        employer_mpf=mpf["employer_mpf"],
        employee_mpf=mpf["employee_mpf"],
        net_pay=mpf["net_pay"],
        mpf_scheme_name=mpf_scheme_name,
        payment_date=payment_date,
        created_by=actor_id,
        updated_by=actor_id,
    )
    db.add(record)
    await db.flush()
    await db.refresh(record)

    await emit(
        db,
        action="salary_record.created",
        entity_type="salary_record",
        entity_id=record.id,
        actor_type="user",
        actor_id=actor_id,
        tenant_id=tenant_id,
        after={
            "gross_salary": str(gross_salary),
            "employer_mpf": str(mpf["employer_mpf"]),
            "employee_mpf": str(mpf["employee_mpf"]),
            "net_pay": str(mpf["net_pay"]),
        },
    )
    log.info("salary_record.created", tenant_id=tenant_id, record_id=record.id)
    return record


async def list_salary_records(
    db: AsyncSession,
    tenant_id: str,
    *,
    period_id: str | None = None,
    employee_contact_id: str | None = None,
    limit: int = 50,
    cursor: str | None = None,
) -> list[SalaryRecord]:
    """List salary records for a tenant."""
    q = select(SalaryRecord).where(SalaryRecord.tenant_id == tenant_id)
    if period_id:
        q = q.where(SalaryRecord.period_id == period_id)
    if employee_contact_id:
        q = q.where(SalaryRecord.employee_contact_id == employee_contact_id)
    if cursor:
        q = q.where(SalaryRecord.id > cursor)
    q = q.order_by(SalaryRecord.created_at.desc(), SalaryRecord.id).limit(limit)
    result = await db.execute(q)
    return list(result.scalars())


async def mpf_summary(
    db: AsyncSession,
    tenant_id: str,
    *,
    period_id: str,
) -> dict:
    """Return MPF summary totals for a period."""
    result = await db.execute(
        select(
            func.count(SalaryRecord.id).label("record_count"),
            func.coalesce(func.sum(SalaryRecord.gross_salary), 0).label("total_gross"),
            func.coalesce(func.sum(SalaryRecord.employer_mpf), 0).label("total_employer_mpf"),
            func.coalesce(func.sum(SalaryRecord.employee_mpf), 0).label("total_employee_mpf"),
            func.coalesce(func.sum(SalaryRecord.net_pay), 0).label("total_net_pay"),
        ).where(
            SalaryRecord.tenant_id == tenant_id,
            SalaryRecord.period_id == period_id,
        )
    )
    row = result.one()
    return {
        "period_id": period_id,
        "record_count": int(row.record_count),
        "total_gross": str(Decimal(str(row.total_gross))),
        "total_employer_mpf": str(Decimal(str(row.total_employer_mpf))),
        "total_employee_mpf": str(Decimal(str(row.total_employee_mpf))),
        "total_net_pay": str(Decimal(str(row.total_net_pay))),
        "generated_at": datetime.now(tz=UTC).isoformat(),
    }
