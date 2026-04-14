"""Reports API — trial balance and general ledger."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, HTTPException, Query, status

from app.api.v1.deps import DbSession, TenantId
from app.api.v1.schemas import (
    GLLineResponse,
    GLReportResponse,
    TrialBalanceResponse,
    TrialBalanceRowResponse,
)
from app.services.reports import general_ledger, trial_balance

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/trial-balance", response_model=TrialBalanceResponse)
async def trial_balance_endpoint(
    db: DbSession,
    tenant_id: TenantId,
    as_of: date = Query(..., description="Balance as of this date (inclusive)"),
) -> TrialBalanceResponse:
    report = await trial_balance(db, tenant_id=tenant_id, as_of=as_of)
    rows = [
        TrialBalanceRowResponse(
            account_id=r.account_id,
            code=r.code,
            name=r.name,
            type=r.type,
            normal_balance=r.normal_balance,
            total_debit=str(r.total_debit),
            total_credit=str(r.total_credit),
            balance=str(r.balance),
        )
        for r in report.rows
    ]
    return TrialBalanceResponse(
        as_of=report.as_of,
        tenant_id=report.tenant_id,
        total_debit=str(report.total_debit),
        total_credit=str(report.total_credit),
        is_balanced=report.is_balanced,
        generated_at=report.generated_at,
        rows=rows,
    )


@router.get("/general-ledger", response_model=GLReportResponse)
async def general_ledger_endpoint(
    db: DbSession,
    tenant_id: TenantId,
    account_id: str = Query(...),
    from_date: date = Query(...),
    to_date: date = Query(...),
) -> GLReportResponse:
    if from_date > to_date:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="from_date must be on or before to_date",
        )
    try:
        report = await general_ledger(
            db,
            tenant_id=tenant_id,
            account_id=account_id,
            from_date=from_date,
            to_date=to_date,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    lines = [
        GLLineResponse(
            date=ln.date,
            journal_number=ln.journal_number,
            journal_id=ln.journal_id,
            description=ln.description,
            debit=str(ln.debit),
            credit=str(ln.credit),
            running_balance=str(ln.running_balance),
        )
        for ln in report.lines
    ]
    return GLReportResponse(
        account_id=report.account_id,
        account_code=report.account_code,
        account_name=report.account_name,
        normal_balance=report.normal_balance,
        from_date=report.from_date,
        to_date=report.to_date,
        opening_balance=str(report.opening_balance),
        closing_balance=str(report.closing_balance),
        lines=lines,
    )
