"""Accounts API — CRUD and archive."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status

from app.api.v1.deps import ActorId, DbSession, TenantId
from app.api.v1.schemas import (
    AccountCreate,
    AccountListResponse,
    AccountResponse,
    AccountUpdate,
    ProblemDetail,
)
from app.services.accounts import (
    AccountCodeConflictError,
    AccountInUseError,
    AccountNotFoundError,
    archive_account,
    create_account,
    get_account,
    list_accounts,
    update_account,
)

router = APIRouter(prefix="/accounts", tags=["accounts"])

# Default Chart of Accounts template (US business)
_DEFAULT_COA = [
    {"code": "1000", "name": "Cash",                       "type": "asset",     "subtype": "bank",         "normal_balance": "debit"},
    {"code": "1100", "name": "Accounts Receivable",         "type": "asset",     "subtype": "receivable",   "normal_balance": "debit"},
    {"code": "1200", "name": "Inventory",                   "type": "asset",     "subtype": "inventory",    "normal_balance": "debit"},
    {"code": "1500", "name": "Prepaid Expenses",            "type": "asset",     "subtype": "prepaid",      "normal_balance": "debit"},
    {"code": "1900", "name": "Fixed Assets",                "type": "asset",     "subtype": "fixed_asset",  "normal_balance": "debit"},
    {"code": "2000", "name": "Accounts Payable",            "type": "liability", "subtype": "payable",      "normal_balance": "credit"},
    {"code": "2100", "name": "Sales Tax Payable",           "type": "liability", "subtype": "tax",          "normal_balance": "credit"},
    {"code": "2200", "name": "Payroll Liabilities",         "type": "liability", "subtype": "payroll",      "normal_balance": "credit"},
    {"code": "2500", "name": "Loans Payable",               "type": "liability", "subtype": "loan",         "normal_balance": "credit"},
    {"code": "3000", "name": "Common Stock",                "type": "equity",    "subtype": "equity",       "normal_balance": "credit"},
    {"code": "3100", "name": "Retained Earnings",           "type": "equity",    "subtype": "retained",     "normal_balance": "credit"},
    {"code": "4000", "name": "Sales Revenue",               "type": "revenue",   "subtype": "sales",        "normal_balance": "credit"},
    {"code": "4100", "name": "Service Revenue",             "type": "revenue",   "subtype": "service",      "normal_balance": "credit"},
    {"code": "4200", "name": "Other Income",                "type": "revenue",   "subtype": "other",        "normal_balance": "credit"},
    {"code": "5000", "name": "Cost of Goods Sold",          "type": "expense",   "subtype": "cogs",         "normal_balance": "debit"},
    {"code": "6000", "name": "Salaries & Wages",            "type": "expense",   "subtype": "payroll",      "normal_balance": "debit"},
    {"code": "6100", "name": "Rent Expense",                "type": "expense",   "subtype": "facilities",   "normal_balance": "debit"},
    {"code": "6200", "name": "Utilities Expense",           "type": "expense",   "subtype": "utilities",    "normal_balance": "debit"},
    {"code": "6300", "name": "Office Supplies",             "type": "expense",   "subtype": "supplies",     "normal_balance": "debit"},
    {"code": "6400", "name": "Marketing & Advertising",     "type": "expense",   "subtype": "marketing",    "normal_balance": "debit"},
    {"code": "6500", "name": "Travel & Entertainment",      "type": "expense",   "subtype": "travel",       "normal_balance": "debit"},
    {"code": "6600", "name": "Depreciation Expense",        "type": "expense",   "subtype": "depreciation", "normal_balance": "debit"},
    {"code": "6700", "name": "Interest Expense",            "type": "expense",   "subtype": "interest",     "normal_balance": "debit"},
    {"code": "6800", "name": "Bank Fees",                   "type": "expense",   "subtype": "bank_charges", "normal_balance": "debit"},
    {"code": "6900", "name": "Other Expenses",              "type": "expense",   "subtype": "other",        "normal_balance": "debit"},
]


@router.post(
    "",
    response_model=AccountResponse,
    status_code=status.HTTP_201_CREATED,
    responses={409: {"model": ProblemDetail}},
)
async def create_account_endpoint(
    body: AccountCreate,
    db: DbSession,
    tenant_id: TenantId,
    actor_id: ActorId,
) -> AccountResponse:
    try:
        account = await create_account(
            db,
            tenant_id=tenant_id,
            code=body.code,
            name=body.name,
            type=body.type,
            subtype=body.subtype,
            normal_balance=body.normal_balance,
            parent_id=body.parent_id,
            currency=body.currency,
            description=body.description,
            actor_id=actor_id,
        )
        await db.commit()
    except AccountCodeConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except AccountNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return AccountResponse.model_validate(account)


@router.get("", response_model=AccountListResponse)
async def list_accounts_endpoint(
    db: DbSession,
    tenant_id: TenantId,
    include_inactive: bool = Query(default=False),
) -> AccountListResponse:
    accounts = await list_accounts(db, tenant_id=tenant_id, include_inactive=include_inactive)
    return AccountListResponse(
        items=[AccountResponse.model_validate(a) for a in accounts],
        total=len(accounts),
    )


@router.get("/{account_id}", response_model=AccountResponse)
async def get_account_endpoint(
    account_id: str,
    db: DbSession,
    tenant_id: TenantId,
) -> AccountResponse:
    try:
        account = await get_account(db, account_id=account_id, tenant_id=tenant_id)
    except AccountNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return AccountResponse.model_validate(account)


@router.patch("/{account_id}", response_model=AccountResponse)
async def update_account_endpoint(
    account_id: str,
    body: AccountUpdate,
    db: DbSession,
    tenant_id: TenantId,
    actor_id: ActorId,
) -> AccountResponse:
    try:
        account = await update_account(
            db,
            account_id=account_id,
            tenant_id=tenant_id,
            name=body.name,
            description=body.description,
            actor_id=actor_id,
        )
        await db.commit()
    except AccountNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return AccountResponse.model_validate(account)


@router.delete("/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
async def archive_account_endpoint(
    account_id: str,
    db: DbSession,
    tenant_id: TenantId,
    actor_id: ActorId,
) -> None:
    try:
        await archive_account(db, account_id=account_id, tenant_id=tenant_id, actor_id=actor_id)
        await db.commit()
    except AccountNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except AccountInUseError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.post("/seed-default", response_model=AccountListResponse, status_code=status.HTTP_201_CREATED)
async def seed_default_coa_endpoint(
    db: DbSession,
    tenant_id: TenantId,
    actor_id: ActorId,
) -> AccountListResponse:
    """Seed a default Chart of Accounts for a new tenant. No-op (returns existing) if already populated."""
    existing = await list_accounts(db, tenant_id=tenant_id, include_inactive=True)
    if existing:
        return AccountListResponse(items=[AccountResponse.model_validate(a) for a in existing], total=len(existing))

    created = []
    for spec in _DEFAULT_COA:
        account = await create_account(
            db,
            tenant_id=tenant_id,
            code=spec["code"],
            name=spec["name"],
            type=spec["type"],
            subtype=spec["subtype"],
            normal_balance=spec["normal_balance"],
            is_system=False,
            actor_id=actor_id,
        )
        created.append(account)
    await db.commit()

    # Also provision accounting periods (current month ± 3 months, 24 months forward)
    try:
        from datetime import date
        import calendar
        from app.services.periods import provision_periods
        from app.infra.models import Tenant as TenantModel
        from sqlalchemy import select as sa_select
        result = await db.execute(sa_select(TenantModel).where(TenantModel.id == tenant_id))
        tenant_row = result.scalar_one_or_none()
        currency = tenant_row.functional_currency if tenant_row else "USD"
        fiscal_start = tenant_row.fiscal_year_start_month if tenant_row else 1
        today = date.today()
        m = today.month - 3
        y = today.year
        while m <= 0:
            m += 12
            y -= 1
        from_date = date(y, m, 1)
        await provision_periods(db, tenant_id=tenant_id, functional_currency=currency,
                                fiscal_year_start_month=fiscal_start, from_date=from_date, months=24)
        await db.commit()
    except Exception:  # noqa: BLE001 — periods are optional; don't fail CoA creation
        pass

    return AccountListResponse(items=[AccountResponse.model_validate(a) for a in created], total=len(created))
