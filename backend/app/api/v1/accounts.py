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


@router.post("/seed-demo", status_code=status.HTTP_201_CREATED)
async def seed_demo_endpoint(
    db: DbSession,
    tenant_id: TenantId,
    actor_id: ActorId,
) -> dict:
    """Seed demo contacts, KYC records, tax codes, and journal entries.

    No-op if >= 3 contacts already exist for tenant.
    Returns counts of created records.
    """
    from datetime import date as _date
    from decimal import Decimal

    from sqlalchemy import func as sa_func
    from sqlalchemy import select as sa_select

    from app.infra.models import Contact, ContactKyc, JournalEntry, JournalLine, Period, TaxCode
    from app.services.contacts import create_contact

    # Guard: skip if tenant already has contacts seeded
    contact_count = await db.scalar(
        sa_select(sa_func.count(Contact.id)).where(
            Contact.tenant_id == tenant_id,
            Contact.is_archived.is_(False),
        )
    )
    if (contact_count or 0) >= 3:
        return {"seeded": False, "reason": "contacts already exist"}

    # ── Contacts ──────────────────────────────────────────────────────────────
    _CONTACTS = [
        {"contact_type": "customer", "name": "Acme Corporation",    "currency": "USD"},
        {"contact_type": "customer", "name": "TechStart Ltd",       "currency": "USD"},
        {"contact_type": "customer", "name": "Global Traders HK",   "currency": "HKD"},
        {"contact_type": "supplier", "name": "Office Depot",        "currency": "USD"},
        {"contact_type": "supplier", "name": "AWS Cloud Services",  "currency": "USD"},
    ]
    contacts_created: list[Contact] = []
    for spec in _CONTACTS:
        c = await create_contact(
            db,
            tenant_id,
            actor_id,
            contact_type=spec["contact_type"],
            name=spec["name"],
            currency=spec["currency"],
        )
        contacts_created.append(c)

    await db.flush()

    # Map by name for KYC seeding
    by_name = {c.name: c for c in contacts_created}

    # ── KYC records ───────────────────────────────────────────────────────────
    _KYC_SEED = [
        {
            "name":             "Acme Corporation",
            "kyc_status":       "approved",
            "sanctions_status": "clear",
            "id_type":          "passport",
            "id_number":        "P12345678",
            "id_expiry_date":   _date(2026, 8, 15),
            "poa_type":         "bank_statement",
            "poa_date":         _date(2024, 3, 10),
            "last_review_date": _date(2024, 3, 10),
            "next_review_date": _date(2027, 3, 10),
        },
        {
            "name":             "TechStart Ltd",
            "kyc_status":       "pending",
            "sanctions_status": "not_checked",
            "id_type":          "national_id",
            "id_number":        "NI9876543",
            "id_expiry_date":   _date(2025, 5, 20),   # expired!
            "poa_type":         "utility_bill",
            "poa_date":         _date(2022, 11, 1),   # stale (> 3 years)
            "last_review_date": _date(2022, 11, 1),
            "next_review_date": _date(2023, 11, 1),
        },
        {
            "name":             "Global Traders HK",
            "kyc_status":       "approved",
            "sanctions_status": "flagged",
            "id_type":          "passport",
            "id_number":        "HK8881234",
            "id_expiry_date":   _date(2027, 2, 28),
            "poa_type":         "tax_document",
            "poa_date":         _date(2024, 1, 15),
            "last_review_date": _date(2024, 1, 15),
            "next_review_date": _date(2025, 1, 15),
            "notes":            "Flagged by OFAC screening 2024-01-20. Under investigation.",
        },
        {
            "name":             "Office Depot",
            "kyc_status":       "approved",
            "sanctions_status": "clear",
            "id_type":          "drivers_license",
            "id_number":        "DL-OD-4321",
            "id_expiry_date":   _date(2028, 6, 30),
            "poa_type":         "bank_statement",
            "poa_date":         _date(2024, 6, 1),
            "last_review_date": _date(2024, 6, 1),
            "next_review_date": _date(2027, 6, 1),
        },
        {
            "name":             "AWS Cloud Services",
            "kyc_status":       "approved",
            "sanctions_status": "clear",
            "id_type":          "other",
            "id_number":        "AWS-CORP-001",
            "id_expiry_date":   _date(2029, 12, 31),
            "poa_type":         "tax_document",
            "poa_date":         _date(2024, 4, 1),
            "last_review_date": _date(2024, 4, 1),
            "next_review_date": _date(2027, 4, 1),
        },
    ]

    for spec in _KYC_SEED:
        contact = by_name.get(spec["name"])
        if not contact:
            continue
        kyc = ContactKyc(
            tenant_id=tenant_id,
            contact_id=contact.id,
            id_type=spec.get("id_type"),
            id_number=spec.get("id_number"),
            id_expiry_date=spec.get("id_expiry_date"),
            poa_type=spec.get("poa_type"),
            poa_date=spec.get("poa_date"),
            sanctions_status=spec.get("sanctions_status", "not_checked"),
            kyc_status=spec.get("kyc_status", "pending"),
            last_review_date=spec.get("last_review_date"),
            next_review_date=spec.get("next_review_date"),
            notes=spec.get("notes"),
            created_by=actor_id,
            updated_by=actor_id,
        )
        db.add(kyc)

    await db.flush()

    # ── Tax codes ─────────────────────────────────────────────────────────────
    _TAX_CODES = [
        {"code": "DEMO_GST",   "name": "GST 10% (AU)",      "rate": Decimal("0.100000"), "tax_type": "output", "country": "AU"},
        {"code": "DEMO_VAT",   "name": "VAT 20% (GB)",       "rate": Decimal("0.200000"), "tax_type": "output", "country": "GB"},
        {"code": "DEMO_USTAX", "name": "Sales Tax 8% (US)", "rate": Decimal("0.080000"), "tax_type": "output", "country": "US"},
    ]
    for tc_spec in _TAX_CODES:
        exists = await db.scalar(
            sa_select(TaxCode.id).where(
                TaxCode.tenant_id == tenant_id,
                TaxCode.code == tc_spec["code"],
            )
        )
        if not exists:
            tc = TaxCode(
                tenant_id=tenant_id,
                code=tc_spec["code"],
                name=tc_spec["name"],
                rate=tc_spec["rate"],
                tax_type=tc_spec["tax_type"],
                country=tc_spec["country"],
                created_by=actor_id,
                updated_by=actor_id,
            )
            db.add(tc)

    await db.flush()

    # ── Journal entries (only if periods exist) ───────────────────────────────
    period_result = await db.execute(
        sa_select(Period).where(
            Period.tenant_id == tenant_id,
            Period.status == "open",
        ).order_by(Period.start_date).limit(1)
    )
    period = period_result.scalar_one_or_none()

    if period:
        _now_ts = __import__("datetime").datetime.now(tz=__import__("datetime").timezone.utc)

        # Check existing JE count to avoid duplicates
        je_count = await db.scalar(
            sa_select(sa_func.count(JournalEntry.id)).where(
                JournalEntry.tenant_id == tenant_id,
            )
        )

        if (je_count or 0) == 0:
            # ── Opening balance JE ────────────────────────────────────────────
            # Get account IDs
            from app.infra.models import Account
            cash_acct = await db.scalar(
                sa_select(Account).where(
                    Account.tenant_id == tenant_id, Account.code == "1000"
                )
            )
            equity_acct = await db.scalar(
                sa_select(Account).where(
                    Account.tenant_id == tenant_id, Account.code == "3000"
                )
            )
            revenue_acct = await db.scalar(
                sa_select(Account).where(
                    Account.tenant_id == tenant_id, Account.code == "4000"
                )
            )
            expense_acct = await db.scalar(
                sa_select(Account).where(
                    Account.tenant_id == tenant_id, Account.code == "6000"
                )
            )

            if cash_acct and equity_acct and revenue_acct and expense_acct:
                # JE-1: Opening balance
                je1 = JournalEntry(
                    tenant_id=tenant_id,
                    number="JE-DEMO-001",
                    date=_now_ts,
                    period_id=period.id,
                    description="Opening balance — demo seed",
                    source_type="manual",
                    status="posted",
                    total_debit=Decimal("50000.0000"),
                    total_credit=Decimal("50000.0000"),
                    currency="USD",
                    posted_at=_now_ts,
                    posted_by=actor_id,
                    created_by=actor_id,
                    updated_by=actor_id,
                )
                db.add(je1)
                await db.flush()
                db.add(JournalLine(
                    tenant_id=tenant_id,
                    journal_entry_id=je1.id,
                    line_no=1,
                    account_id=cash_acct.id,
                    description="Cash deposit",
                    debit=Decimal("50000.0000"),
                    credit=Decimal("0"),
                    currency="USD",
                    fx_rate=Decimal("1"),
                    functional_debit=Decimal("50000.0000"),
                    functional_credit=Decimal("0"),
                ))
                db.add(JournalLine(
                    tenant_id=tenant_id,
                    journal_entry_id=je1.id,
                    line_no=2,
                    account_id=equity_acct.id,
                    description="Common stock issued",
                    debit=Decimal("0"),
                    credit=Decimal("50000.0000"),
                    currency="USD",
                    fx_rate=Decimal("1"),
                    functional_debit=Decimal("0"),
                    functional_credit=Decimal("50000.0000"),
                ))

                # JE-2: Revenue
                je2 = JournalEntry(
                    tenant_id=tenant_id,
                    number="JE-DEMO-002",
                    date=_now_ts,
                    period_id=period.id,
                    description="Sales revenue — Acme Corporation",
                    source_type="manual",
                    status="posted",
                    total_debit=Decimal("12500.0000"),
                    total_credit=Decimal("12500.0000"),
                    currency="USD",
                    posted_at=_now_ts,
                    posted_by=actor_id,
                    created_by=actor_id,
                    updated_by=actor_id,
                )
                db.add(je2)
                await db.flush()
                ar_acct = await db.scalar(
                    sa_select(Account).where(
                        Account.tenant_id == tenant_id, Account.code == "1100"
                    )
                )
                if ar_acct:
                    db.add(JournalLine(
                        tenant_id=tenant_id,
                        journal_entry_id=je2.id,
                        line_no=1,
                        account_id=ar_acct.id,
                        description="AR - Acme Corp invoice",
                        debit=Decimal("12500.0000"),
                        credit=Decimal("0"),
                        currency="USD",
                        fx_rate=Decimal("1"),
                        functional_debit=Decimal("12500.0000"),
                        functional_credit=Decimal("0"),
                    ))
                    db.add(JournalLine(
                        tenant_id=tenant_id,
                        journal_entry_id=je2.id,
                        line_no=2,
                        account_id=revenue_acct.id,
                        description="Sales revenue",
                        debit=Decimal("0"),
                        credit=Decimal("12500.0000"),
                        currency="USD",
                        fx_rate=Decimal("1"),
                        functional_debit=Decimal("0"),
                        functional_credit=Decimal("12500.0000"),
                    ))

                # JE-3: Expense
                je3 = JournalEntry(
                    tenant_id=tenant_id,
                    number="JE-DEMO-003",
                    date=_now_ts,
                    period_id=period.id,
                    description="Office supplies expense — Office Depot",
                    source_type="manual",
                    status="posted",
                    total_debit=Decimal("3200.0000"),
                    total_credit=Decimal("3200.0000"),
                    currency="USD",
                    posted_at=_now_ts,
                    posted_by=actor_id,
                    created_by=actor_id,
                    updated_by=actor_id,
                )
                db.add(je3)
                await db.flush()
                ap_acct = await db.scalar(
                    sa_select(Account).where(
                        Account.tenant_id == tenant_id, Account.code == "2000"
                    )
                )
                if ap_acct:
                    db.add(JournalLine(
                        tenant_id=tenant_id,
                        journal_entry_id=je3.id,
                        line_no=1,
                        account_id=expense_acct.id,
                        description="Office supplies",
                        debit=Decimal("3200.0000"),
                        credit=Decimal("0"),
                        currency="USD",
                        fx_rate=Decimal("1"),
                        functional_debit=Decimal("3200.0000"),
                        functional_credit=Decimal("0"),
                    ))
                    db.add(JournalLine(
                        tenant_id=tenant_id,
                        journal_entry_id=je3.id,
                        line_no=2,
                        account_id=ap_acct.id,
                        description="AP - Office Depot",
                        debit=Decimal("0"),
                        credit=Decimal("3200.0000"),
                        currency="USD",
                        fx_rate=Decimal("1"),
                        functional_debit=Decimal("0"),
                        functional_credit=Decimal("3200.0000"),
                    ))

    await db.commit()
    return {
        "seeded": True,
        "contacts": len(contacts_created),
        "kyc_records": len(_KYC_SEED),
        "tax_codes": len(_TAX_CODES),
    }


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

        from sqlalchemy import select as sa_select

        from app.infra.models import Tenant as TenantModel
        from app.services.periods import provision_periods
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
    except Exception:  # noqa: BLE001, S110 — periods are optional; don't fail CoA creation
        pass

    return AccountListResponse(items=[AccountResponse.model_validate(a) for a in created], total=len(created))
