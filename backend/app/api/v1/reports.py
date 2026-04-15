"""Reports API — trial balance, general ledger, dashboard, and P&L."""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import text

from app.api.v1.deps import DbSession, TenantId
from app.api.v1.schemas import (
    AgingResponse,
    AgingRowResponse,
    BalanceSheetLineResponse,
    BalanceSheetResponse,
    BalanceSheetSectionResponse,
    CashFlowLineResponse,
    CashFlowResponse,
    DashboardResponse,
    GLLineResponse,
    GLReportResponse,
    PLLineResponse,
    PLResponse,
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


@router.get("/dashboard", response_model=DashboardResponse)
async def dashboard_endpoint(
    db: DbSession,
    tenant_id: TenantId,
) -> DashboardResponse:
    # Cash balance: sum(debit - credit) on bank subtype accounts
    cash_row = await db.execute(
        text("""
            SELECT COALESCE(SUM(jl.debit - jl.credit), 0) AS cash_balance
            FROM journal_lines jl
            JOIN accounts a ON a.id = jl.account_id
            JOIN journal_entries je ON je.id = jl.journal_entry_id
            WHERE a.subtype = 'bank'
              AND je.status = 'posted'
        """)
    )
    cash_balance = Decimal(str(cash_row.scalar() or 0))

    # AR: balance on account code 1100
    ar_row = await db.execute(
        text("""
            SELECT COALESCE(SUM(jl.debit - jl.credit), 0) AS ar_balance
            FROM journal_lines jl
            JOIN accounts a ON a.id = jl.account_id
            JOIN journal_entries je ON je.id = jl.journal_entry_id
            WHERE a.code = '1100'
              AND je.status = 'posted'
        """)
    )
    accounts_receivable = Decimal(str(ar_row.scalar() or 0))

    # AP: balance on account code 2000 (credit normal, so credit - debit)
    ap_row = await db.execute(
        text("""
            SELECT COALESCE(SUM(jl.credit - jl.debit), 0) AS ap_balance
            FROM journal_lines jl
            JOIN accounts a ON a.id = jl.account_id
            JOIN journal_entries je ON je.id = jl.journal_entry_id
            WHERE a.code = '2000'
              AND je.status = 'posted'
        """)
    )
    accounts_payable = Decimal(str(ap_row.scalar() or 0))

    # Revenue MTD: total credit on revenue accounts for current month
    today = date.today()
    month_start = today.replace(day=1)
    rev_row = await db.execute(
        text("""
            SELECT COALESCE(SUM(jl.credit - jl.debit), 0) AS revenue_mtd
            FROM journal_lines jl
            JOIN accounts a ON a.id = jl.account_id
            JOIN journal_entries je ON je.id = jl.journal_entry_id
            WHERE a.type = 'revenue'
              AND je.status = 'posted'
              AND je.date >= :month_start
              AND je.date <= :today
        """),
        {"month_start": month_start, "today": today},
    )
    revenue_mtd = Decimal(str(rev_row.scalar() or 0))

    # Expenses MTD: total debit on expense accounts for current month
    exp_row = await db.execute(
        text("""
            SELECT COALESCE(SUM(jl.debit - jl.credit), 0) AS expenses_mtd
            FROM journal_lines jl
            JOIN accounts a ON a.id = jl.account_id
            JOIN journal_entries je ON je.id = jl.journal_entry_id
            WHERE a.type = 'expense'
              AND je.status = 'posted'
              AND je.date >= :month_start
              AND je.date <= :today
        """),
        {"month_start": month_start, "today": today},
    )
    expenses_mtd = Decimal(str(exp_row.scalar() or 0))

    # Invoices overdue
    inv_row = await db.execute(
        text("""
            SELECT COUNT(*) AS overdue_count
            FROM invoices
            WHERE status IN ('authorised', 'sent', 'partial')
              AND due_date IS NOT NULL
              AND due_date < :today
        """),
        {"today": str(today)},
    )
    invoices_overdue = int(inv_row.scalar() or 0)

    # Bills awaiting approval
    bills_row = await db.execute(
        text("""
            SELECT COUNT(*) AS awaiting_count
            FROM bills
            WHERE status = 'awaiting_approval'
        """)
    )
    bills_awaiting_approval = int(bills_row.scalar() or 0)

    def fmt(d: Decimal) -> str:
        return f"{d:.2f}"

    return DashboardResponse(
        cash_balance=fmt(cash_balance),
        accounts_receivable=fmt(accounts_receivable),
        accounts_payable=fmt(accounts_payable),
        revenue_mtd=fmt(revenue_mtd),
        expenses_mtd=fmt(expenses_mtd),
        invoices_overdue=invoices_overdue,
        bills_awaiting_approval=bills_awaiting_approval,
        generated_at=datetime.now(tz=timezone.utc),
    )


@router.get("/pl", response_model=PLResponse)
async def pl_endpoint(
    db: DbSession,
    tenant_id: TenantId,
    from_date: date = Query(..., description="Start date (inclusive)"),
    to_date: date = Query(..., description="End date (inclusive)"),
) -> PLResponse:
    if from_date > to_date:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="from_date must be on or before to_date",
        )

    rows = await db.execute(
        text("""
            SELECT
                a.id AS account_id,
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
              AND je.date >= :from_date
              AND je.date <= :to_date
            GROUP BY a.id, a.code, a.name, a.type, a.subtype
            ORDER BY a.type, a.code
        """),
        {"from_date": from_date, "to_date": to_date},
    )
    result = rows.fetchall()

    revenue_lines: list[PLLineResponse] = []
    expense_lines: list[PLLineResponse] = []
    total_revenue = Decimal("0")
    total_expenses = Decimal("0")

    for row in result:
        if row.type == "revenue":
            balance = Decimal(str(row.net_credit))
            total_revenue += balance
            revenue_lines.append(
                PLLineResponse(
                    account_id=str(row.account_id),
                    code=row.code,
                    name=row.name,
                    subtype=row.subtype,
                    balance=f"{balance:.2f}",
                )
            )
        elif row.type == "expense":
            balance = Decimal(str(row.net_debit))
            total_expenses += balance
            expense_lines.append(
                PLLineResponse(
                    account_id=str(row.account_id),
                    code=row.code,
                    name=row.name,
                    subtype=row.subtype,
                    balance=f"{balance:.2f}",
                )
            )

    net_profit = total_revenue - total_expenses

    return PLResponse(
        from_date=from_date,
        to_date=to_date,
        total_revenue=f"{total_revenue:.2f}",
        total_expenses=f"{total_expenses:.2f}",
        net_profit=f"{net_profit:.2f}",
        is_profitable=net_profit >= Decimal("0"),
        revenue_lines=revenue_lines,
        expense_lines=expense_lines,
        generated_at=datetime.now(tz=timezone.utc),
    )


@router.get("/balance-sheet", response_model=BalanceSheetResponse)
async def balance_sheet_endpoint(
    db: DbSession,
    tenant_id: TenantId,
    as_of: date = Query(..., description="Balance sheet as of this date (inclusive)"),
) -> BalanceSheetResponse:
    rows = await db.execute(
        text("""
            SELECT
                a.id AS account_id,
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
              AND je.date <= :as_of
            GROUP BY a.id, a.code, a.name, a.type, a.subtype
            ORDER BY a.type, a.code
        """),
        {"as_of": as_of},
    )
    result = rows.fetchall()

    asset_lines: list[BalanceSheetLineResponse] = []
    liability_lines: list[BalanceSheetLineResponse] = []
    equity_lines: list[BalanceSheetLineResponse] = []
    total_assets = Decimal("0")
    total_liabilities = Decimal("0")
    total_equity = Decimal("0")

    for row in result:
        td = Decimal(str(row.total_debit))
        tc = Decimal(str(row.total_credit))
        if row.type == "asset":
            balance = td - tc  # debit-normal: positive = asset
            total_assets += balance
            asset_lines.append(
                BalanceSheetLineResponse(
                    account_id=str(row.account_id),
                    code=row.code,
                    name=row.name,
                    subtype=row.subtype,
                    balance=f"{balance:.2f}",
                )
            )
        elif row.type == "liability":
            balance = tc - td  # credit-normal: positive = liability
            total_liabilities += balance
            liability_lines.append(
                BalanceSheetLineResponse(
                    account_id=str(row.account_id),
                    code=row.code,
                    name=row.name,
                    subtype=row.subtype,
                    balance=f"{balance:.2f}",
                )
            )
        elif row.type == "equity":
            balance = tc - td  # credit-normal: positive = equity
            total_equity += balance
            equity_lines.append(
                BalanceSheetLineResponse(
                    account_id=str(row.account_id),
                    code=row.code,
                    name=row.name,
                    subtype=row.subtype,
                    balance=f"{balance:.2f}",
                )
            )

    total_liabilities_and_equity = total_liabilities + total_equity
    is_balanced = abs(total_assets - total_liabilities_and_equity) < Decimal("0.01")

    return BalanceSheetResponse(
        as_of=as_of,
        assets=BalanceSheetSectionResponse(
            total=f"{total_assets:.2f}",
            lines=asset_lines,
        ),
        liabilities=BalanceSheetSectionResponse(
            total=f"{total_liabilities:.2f}",
            lines=liability_lines,
        ),
        equity=BalanceSheetSectionResponse(
            total=f"{total_equity:.2f}",
            lines=equity_lines,
        ),
        total_liabilities_and_equity=f"{total_liabilities_and_equity:.2f}",
        is_balanced=is_balanced,
        generated_at=datetime.now(tz=timezone.utc),
    )


def _aging_bucket(days_overdue: int) -> str:
    if days_overdue <= 0:
        return "current"
    elif days_overdue <= 30:
        return "1-30"
    elif days_overdue <= 60:
        return "31-60"
    elif days_overdue <= 90:
        return "61-90"
    else:
        return "90+"


async def _build_aging_response(
    db: DbSession,
    as_of: date,
    table: str,
    open_statuses: tuple[str, ...],
) -> AgingResponse:
    placeholders = ", ".join(f"'{s}'" for s in open_statuses)
    rows = await db.execute(
        text(f"""
            SELECT
                t.id AS doc_id,
                t.number AS invoice_number,
                t.issue_date,
                t.due_date,
                t.total,
                t.amount_due,
                t.contact_id,
                c.name AS contact_name
            FROM {table} t
            JOIN contacts c ON c.id = t.contact_id
            WHERE t.status IN ({placeholders})
              AND t.amount_due > 0
            ORDER BY t.due_date ASC NULLS LAST, t.issue_date ASC
        """),
    )
    result = rows.fetchall()

    aging_rows: list[AgingRowResponse] = []
    bucket_totals: dict[str, Decimal] = {
        "current": Decimal("0"),
        "1-30": Decimal("0"),
        "31-60": Decimal("0"),
        "61-90": Decimal("0"),
        "90+": Decimal("0"),
    }
    grand_total = Decimal("0")

    for row in result:
        amount_due = Decimal(str(row.amount_due))
        total = Decimal(str(row.total))

        def _to_date(v: object) -> date:
            if isinstance(v, date):
                return v
            # asyncpg may return datetime or str
            from datetime import datetime as _dt
            if isinstance(v, _dt):
                return v.date()
            return date.fromisoformat(str(v))

        due: date | None = None
        if row.due_date is not None:
            due = _to_date(row.due_date)
            days_overdue = max(0, (as_of - due).days)
        else:
            days_overdue = 0

        bucket = _aging_bucket(days_overdue)
        bucket_totals[bucket] += amount_due
        grand_total += amount_due

        issue = _to_date(row.issue_date)
        aging_rows.append(
            AgingRowResponse(
                contact_id=str(row.contact_id),
                contact_name=row.contact_name,
                invoice_number=row.invoice_number,
                issue_date=str(issue),
                due_date=str(due) if due is not None else None,
                total=f"{total:.2f}",
                amount_due=f"{amount_due:.2f}",
                days_overdue=days_overdue,
                bucket=bucket,
            )
        )

    return AgingResponse(
        as_of=as_of,
        current_total=f"{bucket_totals['current']:.2f}",
        bucket_1_30=f"{bucket_totals['1-30']:.2f}",
        bucket_31_60=f"{bucket_totals['31-60']:.2f}",
        bucket_61_90=f"{bucket_totals['61-90']:.2f}",
        bucket_90_plus=f"{bucket_totals['90+']:.2f}",
        grand_total=f"{grand_total:.2f}",
        rows=aging_rows,
        generated_at=datetime.now(tz=timezone.utc),
    )


@router.get("/ar-aging", response_model=AgingResponse)
async def ar_aging_endpoint(
    db: DbSession,
    tenant_id: TenantId,
    as_of: date = Query(..., description="AR aging as of this date"),
) -> AgingResponse:
    return await _build_aging_response(
        db, as_of, "invoices", ("authorised", "sent", "partial")
    )


@router.get("/ap-aging", response_model=AgingResponse)
async def ap_aging_endpoint(
    db: DbSession,
    tenant_id: TenantId,
    as_of: date = Query(..., description="AP aging as of this date"),
) -> AgingResponse:
    return await _build_aging_response(
        db, as_of, "bills", ("approved", "partial")
    )


async def _account_balance_at(db: DbSession, account_type: str, as_of: date) -> Decimal:
    """Return the net balance for accounts of a given type as of a date."""
    row = await db.execute(
        text("""
            SELECT COALESCE(SUM(jl.functional_debit) - SUM(jl.functional_credit), 0) AS net
            FROM journal_lines jl
            JOIN journal_entries je ON je.id = jl.journal_entry_id
            JOIN accounts a ON a.id = jl.account_id
            WHERE a.type = :atype
              AND je.status = 'posted'
              AND je.date <= :as_of
        """),
        {"atype": account_type, "as_of": as_of},
    )
    return Decimal(str(row.scalar() or 0))


async def _account_balance_range_by_code(
    db: DbSession,
    code_prefix_start: str,
    code_prefix_end: str,
    as_of: date,
) -> Decimal:
    """Return net debit-credit balance for accounts whose code falls in [start, end)."""
    row = await db.execute(
        text("""
            SELECT COALESCE(SUM(jl.functional_debit) - SUM(jl.functional_credit), 0) AS net
            FROM journal_lines jl
            JOIN journal_entries je ON je.id = jl.journal_entry_id
            JOIN accounts a ON a.id = jl.account_id
            WHERE a.code >= :start AND a.code < :end
              AND je.status = 'posted'
              AND je.date <= :as_of
        """),
        {"start": code_prefix_start, "end": code_prefix_end, "as_of": as_of},
    )
    return Decimal(str(row.scalar() or 0))


@router.get("/cash-flow", response_model=CashFlowResponse)
async def cash_flow_endpoint(
    db: DbSession,
    tenant_id: TenantId,
    from_date: date = Query(..., description="Start date (inclusive)"),
    to_date: date = Query(..., description="End date (inclusive)"),
) -> CashFlowResponse:
    if from_date > to_date:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="from_date must be on or before to_date",
        )

    from datetime import timedelta

    opening_date = from_date - timedelta(days=1)

    # --- Net profit (indirect method starting point) ---
    pl_row = await db.execute(
        text("""
            SELECT
                COALESCE(SUM(CASE WHEN a.type = 'revenue' THEN jl.functional_credit - jl.functional_debit ELSE 0 END), 0) AS revenue,
                COALESCE(SUM(CASE WHEN a.type = 'expense' THEN jl.functional_debit - jl.functional_credit ELSE 0 END), 0) AS expenses
            FROM journal_lines jl
            JOIN journal_entries je ON je.id = jl.journal_entry_id
            JOIN accounts a ON a.id = jl.account_id
            WHERE a.type IN ('revenue', 'expense')
              AND je.status = 'posted'
              AND je.date >= :from_date
              AND je.date <= :to_date
        """),
        {"from_date": from_date, "to_date": to_date},
    )
    pl_result = pl_row.fetchone()
    net_profit = Decimal(str(pl_result.revenue or 0)) - Decimal(str(pl_result.expenses or 0))

    # --- AR change: opening AR - closing AR (decrease in AR = cash inflow) ---
    ar_open_row = await db.execute(
        text("""
            SELECT COALESCE(SUM(jl.functional_debit) - SUM(jl.functional_credit), 0) AS bal
            FROM journal_lines jl
            JOIN journal_entries je ON je.id = jl.journal_entry_id
            JOIN accounts a ON a.id = jl.account_id
            WHERE a.code = '1100'
              AND je.status = 'posted'
              AND je.date <= :as_of
        """),
        {"as_of": opening_date},
    )
    ar_open = Decimal(str(ar_open_row.scalar() or 0))

    ar_close_row = await db.execute(
        text("""
            SELECT COALESCE(SUM(jl.functional_debit) - SUM(jl.functional_credit), 0) AS bal
            FROM journal_lines jl
            JOIN journal_entries je ON je.id = jl.journal_entry_id
            JOIN accounts a ON a.id = jl.account_id
            WHERE a.code = '1100'
              AND je.status = 'posted'
              AND je.date <= :as_of
        """),
        {"as_of": to_date},
    )
    ar_close = Decimal(str(ar_close_row.scalar() or 0))
    ar_change = ar_open - ar_close  # decrease = cash inflow

    # --- AP change: closing AP - opening AP (increase in AP = cash inflow) ---
    ap_open_row = await db.execute(
        text("""
            SELECT COALESCE(SUM(jl.functional_credit) - SUM(jl.functional_debit), 0) AS bal
            FROM journal_lines jl
            JOIN journal_entries je ON je.id = jl.journal_entry_id
            JOIN accounts a ON a.id = jl.account_id
            WHERE a.code = '2000'
              AND je.status = 'posted'
              AND je.date <= :as_of
        """),
        {"as_of": opening_date},
    )
    ap_open = Decimal(str(ap_open_row.scalar() or 0))

    ap_close_row = await db.execute(
        text("""
            SELECT COALESCE(SUM(jl.functional_credit) - SUM(jl.functional_debit), 0) AS bal
            FROM journal_lines jl
            JOIN journal_entries je ON je.id = jl.journal_entry_id
            JOIN accounts a ON a.id = jl.account_id
            WHERE a.code = '2000'
              AND je.status = 'posted'
              AND je.date <= :as_of
        """),
        {"as_of": to_date},
    )
    ap_close = Decimal(str(ap_close_row.scalar() or 0))
    ap_change = ap_close - ap_open  # increase = cash inflow

    net_operating = net_profit + ar_change + ap_change

    operating_activities = [
        CashFlowLineResponse(label="Net profit", amount=f"{net_profit:.2f}"),
        CashFlowLineResponse(label="Change in accounts receivable", amount=f"{ar_change:.2f}"),
        CashFlowLineResponse(label="Change in accounts payable", amount=f"{ap_change:.2f}"),
        CashFlowLineResponse(label="Net cash from operating activities", amount=f"{net_operating:.2f}", is_subtotal=True),
    ]

    # --- Investing: change in fixed assets (1900-range codes) ---
    fa_open_row = await db.execute(
        text("""
            SELECT COALESCE(SUM(jl.functional_debit) - SUM(jl.functional_credit), 0) AS bal
            FROM journal_lines jl
            JOIN journal_entries je ON je.id = jl.journal_entry_id
            JOIN accounts a ON a.id = jl.account_id
            WHERE a.code >= '1900' AND a.code < '2000'
              AND je.status = 'posted'
              AND je.date <= :as_of
        """),
        {"as_of": opening_date},
    )
    fa_open = Decimal(str(fa_open_row.scalar() or 0))

    fa_close_row = await db.execute(
        text("""
            SELECT COALESCE(SUM(jl.functional_debit) - SUM(jl.functional_credit), 0) AS bal
            FROM journal_lines jl
            JOIN journal_entries je ON je.id = jl.journal_entry_id
            JOIN accounts a ON a.id = jl.account_id
            WHERE a.code >= '1900' AND a.code < '2000'
              AND je.status = 'posted'
              AND je.date <= :as_of
        """),
        {"as_of": to_date},
    )
    fa_close = Decimal(str(fa_close_row.scalar() or 0))
    # Increase in fixed assets = cash outflow (negative)
    net_investing = -(fa_close - fa_open)

    investing_activities = [
        CashFlowLineResponse(label="Change in fixed assets", amount=f"{net_investing:.2f}"),
        CashFlowLineResponse(label="Net cash from investing activities", amount=f"{net_investing:.2f}", is_subtotal=True),
    ]

    # --- Financing: change in loans (2500-range) + owner equity contributions (3000-range) ---
    loans_open_row = await db.execute(
        text("""
            SELECT COALESCE(SUM(jl.functional_credit) - SUM(jl.functional_debit), 0) AS bal
            FROM journal_lines jl
            JOIN journal_entries je ON je.id = jl.journal_entry_id
            JOIN accounts a ON a.id = jl.account_id
            WHERE a.code >= '2500' AND a.code < '3000'
              AND je.status = 'posted'
              AND je.date <= :as_of
        """),
        {"as_of": opening_date},
    )
    loans_open = Decimal(str(loans_open_row.scalar() or 0))

    loans_close_row = await db.execute(
        text("""
            SELECT COALESCE(SUM(jl.functional_credit) - SUM(jl.functional_debit), 0) AS bal
            FROM journal_lines jl
            JOIN journal_entries je ON je.id = jl.journal_entry_id
            JOIN accounts a ON a.id = jl.account_id
            WHERE a.code >= '2500' AND a.code < '3000'
              AND je.status = 'posted'
              AND je.date <= :as_of
        """),
        {"as_of": to_date},
    )
    loans_close = Decimal(str(loans_close_row.scalar() or 0))
    loans_change = loans_close - loans_open  # new borrowings = cash inflow

    equity_open_row = await db.execute(
        text("""
            SELECT COALESCE(SUM(jl.functional_credit) - SUM(jl.functional_debit), 0) AS bal
            FROM journal_lines jl
            JOIN journal_entries je ON je.id = jl.journal_entry_id
            JOIN accounts a ON a.id = jl.account_id
            WHERE a.code >= '3000' AND a.code < '4000'
              AND je.status = 'posted'
              AND je.date <= :as_of
        """),
        {"as_of": opening_date},
    )
    equity_open = Decimal(str(equity_open_row.scalar() or 0))

    equity_close_row = await db.execute(
        text("""
            SELECT COALESCE(SUM(jl.functional_credit) - SUM(jl.functional_debit), 0) AS bal
            FROM journal_lines jl
            JOIN journal_entries je ON je.id = jl.journal_entry_id
            JOIN accounts a ON a.id = jl.account_id
            WHERE a.code >= '3000' AND a.code < '4000'
              AND je.status = 'posted'
              AND je.date <= :as_of
        """),
        {"as_of": to_date},
    )
    equity_close = Decimal(str(equity_close_row.scalar() or 0))
    equity_contributions = equity_close - equity_open  # new equity = cash inflow

    net_financing = loans_change + equity_contributions

    financing_activities = [
        CashFlowLineResponse(label="Change in loans payable", amount=f"{loans_change:.2f}"),
        CashFlowLineResponse(label="Owner equity contributions", amount=f"{equity_contributions:.2f}"),
        CashFlowLineResponse(label="Net cash from financing activities", amount=f"{net_financing:.2f}", is_subtotal=True),
    ]

    net_change = net_operating + net_investing + net_financing

    # --- Cash balances ---
    cash_open_row = await db.execute(
        text("""
            SELECT COALESCE(SUM(jl.functional_debit) - SUM(jl.functional_credit), 0) AS bal
            FROM journal_lines jl
            JOIN journal_entries je ON je.id = jl.journal_entry_id
            JOIN accounts a ON a.id = jl.account_id
            WHERE a.subtype = 'bank'
              AND je.status = 'posted'
              AND je.date <= :as_of
        """),
        {"as_of": opening_date},
    )
    opening_cash = Decimal(str(cash_open_row.scalar() or 0))

    cash_close_row = await db.execute(
        text("""
            SELECT COALESCE(SUM(jl.functional_debit) - SUM(jl.functional_credit), 0) AS bal
            FROM journal_lines jl
            JOIN journal_entries je ON je.id = jl.journal_entry_id
            JOIN accounts a ON a.id = jl.account_id
            WHERE a.subtype = 'bank'
              AND je.status = 'posted'
              AND je.date <= :as_of
        """),
        {"as_of": to_date},
    )
    closing_cash = Decimal(str(cash_close_row.scalar() or 0))

    return CashFlowResponse(
        from_date=from_date,
        to_date=to_date,
        operating_activities=operating_activities,
        investing_activities=investing_activities,
        financing_activities=financing_activities,
        net_operating=f"{net_operating:.2f}",
        net_investing=f"{net_investing:.2f}",
        net_financing=f"{net_financing:.2f}",
        net_change=f"{net_change:.2f}",
        opening_cash=f"{opening_cash:.2f}",
        closing_cash=f"{closing_cash:.2f}",
        generated_at=datetime.now(tz=timezone.utc),
    )
