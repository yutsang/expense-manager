"""Payroll API — salary records + MPF summary (Issue #46)."""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.api.v1.deps import ActorId, DbSession, TenantId
from app.services.payroll import create_salary_record, list_salary_records, mpf_summary

router = APIRouter(prefix="/payroll", tags=["payroll"])


class SalaryRecordCreate(BaseModel):
    employee_contact_id: str
    period_id: str
    gross_salary: str = Field(..., description="Decimal string, e.g. '25000.0000'")
    mpf_scheme_name: str | None = None
    payment_date: str | None = None


class SalaryRecordResponse(BaseModel):
    id: str
    tenant_id: str
    employee_contact_id: str
    period_id: str
    gross_salary: str
    employer_mpf: str
    employee_mpf: str
    net_pay: str
    mpf_scheme_name: str | None = None
    payment_date: str | None = None


class SalaryRecordListResponse(BaseModel):
    items: list[SalaryRecordResponse]


class MpfSummaryResponse(BaseModel):
    period_id: str
    record_count: int
    total_gross: str
    total_employer_mpf: str
    total_employee_mpf: str
    total_net_pay: str
    generated_at: str


def _to_response(rec: object) -> SalaryRecordResponse:
    return SalaryRecordResponse(
        id=rec.id,  # type: ignore[union-attr]
        tenant_id=rec.tenant_id,  # type: ignore[union-attr]
        employee_contact_id=rec.employee_contact_id,  # type: ignore[union-attr]
        period_id=rec.period_id,  # type: ignore[union-attr]
        gross_salary=str(rec.gross_salary),  # type: ignore[union-attr]
        employer_mpf=str(rec.employer_mpf),  # type: ignore[union-attr]
        employee_mpf=str(rec.employee_mpf),  # type: ignore[union-attr]
        net_pay=str(rec.net_pay),  # type: ignore[union-attr]
        mpf_scheme_name=rec.mpf_scheme_name,  # type: ignore[union-attr]
        payment_date=rec.payment_date,  # type: ignore[union-attr]
    )


@router.post(
    "/salary-records",
    response_model=SalaryRecordResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_salary_record_endpoint(
    db: DbSession,
    tenant_id: TenantId,
    actor_id: ActorId,
    body: SalaryRecordCreate,
) -> SalaryRecordResponse:
    try:
        record = await create_salary_record(
            db,
            tenant_id,
            actor_id,
            employee_contact_id=body.employee_contact_id,
            period_id=body.period_id,
            gross_salary=Decimal(body.gross_salary),
            mpf_scheme_name=body.mpf_scheme_name,
            payment_date=body.payment_date,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return _to_response(record)


@router.get("/salary-records", response_model=SalaryRecordListResponse)
async def list_salary_records_endpoint(
    db: DbSession,
    tenant_id: TenantId,
    period_id: str | None = Query(default=None),
    employee_contact_id: str | None = Query(default=None),
    limit: int = Query(default=50, le=200),
    cursor: str | None = Query(default=None),
) -> SalaryRecordListResponse:
    records = await list_salary_records(
        db,
        tenant_id,
        period_id=period_id,
        employee_contact_id=employee_contact_id,
        limit=limit,
        cursor=cursor,
    )
    return SalaryRecordListResponse(items=[_to_response(r) for r in records])


@router.get("/mpf-summary", response_model=MpfSummaryResponse)
async def mpf_summary_endpoint(
    db: DbSession,
    tenant_id: TenantId,
    period_id: str = Query(...),
) -> MpfSummaryResponse:
    data = await mpf_summary(db, tenant_id, period_id=period_id)
    return MpfSummaryResponse(**data)
