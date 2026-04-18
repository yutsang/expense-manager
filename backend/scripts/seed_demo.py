"""
Demo seed script — populates a dev tenant with realistic Dragon Advisory Ltd data.

A Hong Kong professional services firm doing consulting, audit, and tax work.
Uses HKD as functional currency with some USD and GBP transactions.
Covers 6 months of data: Nov 2025 — Apr 2026.

Run from backend/:
  python scripts/seed_demo.py
  python scripts/seed_demo.py --force   # re-seed (deletes existing demo data first)
"""

from __future__ import annotations

import asyncio
import calendar
import os
import sys
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

# Set env vars before any app imports
os.environ.setdefault("SECRET_KEY", "dev-secret-key-at-least-32-chars-long!!")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://aegis:aegis@localhost:5432/aegis_dev")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379")
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-placeholder")

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.core.security import hash_password
from app.infra.models import (
    Account,
    BankAccount,
    BankTransaction,
    Bill,
    BillLine,
    BillingRate,
    Budget,
    BudgetLine,
    Contact,
    ExpenseClaim,
    ExpenseClaimLine,
    FixedAsset,
    FxRate,
    Invoice,
    InvoiceLine,
    Item,
    JournalEntry,
    JournalLine,
    Membership,
    Payment,
    PaymentAllocation,
    Period,
    Project,
    SalaryRecord,
    TaxCode,
    Tenant,
    TimeEntry,
    User,
)

DATABASE_URL = os.environ["DATABASE_URL"]
engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

TENANT_ID = "10000000-0000-0000-0000-000000000001"
ACTOR_ID = "10000000-0000-0000-0000-000000000002"
ACTOR2_ID = "10000000-0000-0000-0000-000000000003"


def _uid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(tz=UTC)


def _dt(iso: str) -> datetime:
    """Parse an ISO date string to a UTC datetime."""
    return datetime.fromisoformat(iso).replace(tzinfo=UTC)


def _d(iso: str) -> date:
    """Parse an ISO date string to a date object."""
    return date.fromisoformat(iso)


# ---------------------------------------------------------------------------
# Chart of Accounts — HK professional services firm
# ---------------------------------------------------------------------------

ACCOUNTS = [
    # Assets
    {"code": "1000", "name": "Cash at Bank — HKD", "type": "asset", "subtype": "bank", "normal_balance": "debit"},
    {"code": "1010", "name": "Cash at Bank — USD", "type": "asset", "subtype": "bank", "normal_balance": "debit"},
    {"code": "1020", "name": "Petty Cash", "type": "asset", "subtype": "bank", "normal_balance": "debit"},
    {"code": "1100", "name": "Accounts Receivable", "type": "asset", "subtype": "receivable", "normal_balance": "debit"},
    {"code": "1200", "name": "Prepayments", "type": "asset", "subtype": "prepaid", "normal_balance": "debit"},
    {"code": "1300", "name": "Staff Advances", "type": "asset", "subtype": "receivable", "normal_balance": "debit"},
    {"code": "1500", "name": "Office Equipment", "type": "asset", "subtype": "fixed_asset", "normal_balance": "debit"},
    {"code": "1510", "name": "Computer Equipment", "type": "asset", "subtype": "fixed_asset", "normal_balance": "debit"},
    {"code": "1520", "name": "Leasehold Improvements", "type": "asset", "subtype": "fixed_asset", "normal_balance": "debit"},
    {"code": "1550", "name": "Accumulated Depreciation — Office Equipment", "type": "asset", "subtype": "fixed_asset", "normal_balance": "credit"},
    {"code": "1560", "name": "Accumulated Depreciation — Computer Equipment", "type": "asset", "subtype": "fixed_asset", "normal_balance": "credit"},
    {"code": "1570", "name": "Accumulated Depreciation — Leasehold Improvements", "type": "asset", "subtype": "fixed_asset", "normal_balance": "credit"},
    # Liabilities
    {"code": "2000", "name": "Accounts Payable", "type": "liability", "subtype": "payable", "normal_balance": "credit"},
    {"code": "2100", "name": "Accrued Expenses", "type": "liability", "subtype": "payable", "normal_balance": "credit"},
    {"code": "2200", "name": "Profits Tax Payable", "type": "liability", "subtype": "tax", "normal_balance": "credit"},
    {"code": "2300", "name": "MPF Payable", "type": "liability", "subtype": "payroll", "normal_balance": "credit"},
    {"code": "2400", "name": "Unearned Revenue", "type": "liability", "subtype": "payable", "normal_balance": "credit"},
    {"code": "2500", "name": "Provision for Audit Fee", "type": "liability", "subtype": "payable", "normal_balance": "credit"},
    # Equity
    {"code": "3000", "name": "Share Capital", "type": "equity", "subtype": "equity", "normal_balance": "credit"},
    {"code": "3100", "name": "Retained Earnings", "type": "equity", "subtype": "retained", "normal_balance": "credit"},
    {"code": "3200", "name": "Current Year Earnings", "type": "equity", "subtype": "retained", "normal_balance": "credit"},
    # Revenue
    {"code": "4000", "name": "Consulting Fees", "type": "revenue", "subtype": "sales", "normal_balance": "credit"},
    {"code": "4100", "name": "Audit Fees", "type": "revenue", "subtype": "sales", "normal_balance": "credit"},
    {"code": "4200", "name": "Tax Advisory Fees", "type": "revenue", "subtype": "sales", "normal_balance": "credit"},
    {"code": "4300", "name": "Training Revenue", "type": "revenue", "subtype": "sales", "normal_balance": "credit"},
    {"code": "4400", "name": "Reimbursable Expenses", "type": "revenue", "subtype": "sales", "normal_balance": "credit"},
    {"code": "4900", "name": "Other Income", "type": "revenue", "subtype": "other", "normal_balance": "credit"},
    {"code": "4910", "name": "FX Gain", "type": "revenue", "subtype": "other", "normal_balance": "credit"},
    # Expenses
    {"code": "5000", "name": "Salaries & Wages", "type": "expense", "subtype": "payroll", "normal_balance": "debit"},
    {"code": "5100", "name": "MPF — Employer Contribution", "type": "expense", "subtype": "payroll", "normal_balance": "debit"},
    {"code": "5200", "name": "Staff Benefits", "type": "expense", "subtype": "payroll", "normal_balance": "debit"},
    {"code": "6000", "name": "Rent", "type": "expense", "subtype": "facilities", "normal_balance": "debit"},
    {"code": "6100", "name": "Utilities", "type": "expense", "subtype": "facilities", "normal_balance": "debit"},
    {"code": "6200", "name": "Insurance", "type": "expense", "subtype": "operating", "normal_balance": "debit"},
    {"code": "6300", "name": "Travel & Transport", "type": "expense", "subtype": "travel", "normal_balance": "debit"},
    {"code": "6400", "name": "Entertainment", "type": "expense", "subtype": "travel", "normal_balance": "debit"},
    {"code": "6500", "name": "Professional Development", "type": "expense", "subtype": "operating", "normal_balance": "debit"},
    {"code": "6600", "name": "Software & Subscriptions", "type": "expense", "subtype": "software", "normal_balance": "debit"},
    {"code": "6700", "name": "Depreciation", "type": "expense", "subtype": "operating", "normal_balance": "debit"},
    {"code": "6800", "name": "Bank Charges", "type": "expense", "subtype": "operating", "normal_balance": "debit"},
    {"code": "6900", "name": "Printing & Stationery", "type": "expense", "subtype": "operating", "normal_balance": "debit"},
    {"code": "7000", "name": "Courier & Postage", "type": "expense", "subtype": "operating", "normal_balance": "debit"},
    {"code": "7100", "name": "Legal & Professional Fees", "type": "expense", "subtype": "professional", "normal_balance": "debit"},
    {"code": "7200", "name": "Telephone & Internet", "type": "expense", "subtype": "facilities", "normal_balance": "debit"},
    {"code": "7300", "name": "Cleaning & Maintenance", "type": "expense", "subtype": "facilities", "normal_balance": "debit"},
    {"code": "7900", "name": "FX Loss", "type": "expense", "subtype": "other", "normal_balance": "debit"},
    {"code": "7910", "name": "Miscellaneous Expenses", "type": "expense", "subtype": "other", "normal_balance": "debit"},
]


async def seed_accounts(db: AsyncSession) -> dict[str, str]:
    """Create all accounts, returns code -> id mapping."""
    code_to_id: dict[str, str] = {}
    for a in ACCOUNTS:
        acc = Account(
            id=_uid(),
            tenant_id=TENANT_ID,
            code=a["code"],
            name=a["name"],
            type=a["type"],
            subtype=a["subtype"],
            normal_balance=a["normal_balance"],
            currency="HKD",
            is_active=True,
            is_system=False,
            created_by=ACTOR_ID,
            updated_by=ACTOR_ID,
        )
        db.add(acc)
        code_to_id[a["code"]] = acc.id
    await db.flush()
    print(f"  [ok] {len(ACCOUNTS)} accounts")
    return code_to_id


async def seed_periods(db: AsyncSession) -> dict[str, str]:
    """Create 6 monthly periods: Nov 2025 - Apr 2026.
    Nov-Feb hard_closed, Mar-Apr open.
    """
    periods_data = [
        ("2025-11", date(2025, 11, 1), date(2025, 11, 30), "hard_closed"),
        ("2025-12", date(2025, 12, 1), date(2025, 12, 31), "hard_closed"),
        ("2026-01", date(2026, 1, 1), date(2026, 1, 31), "hard_closed"),
        ("2026-02", date(2026, 2, 1), date(2026, 2, 28), "hard_closed"),
        ("2026-03", date(2026, 3, 1), date(2026, 3, 31), "open"),
        ("2026-04", date(2026, 4, 1), date(2026, 4, 30), "open"),
    ]

    period_ids: dict[str, str] = {}
    for name, start, end, period_status in periods_data:
        closed_at = _dt(f"{end.isoformat()}T23:59:59") if period_status == "hard_closed" else None
        p = Period(
            id=_uid(),
            tenant_id=TENANT_ID,
            name=name,
            start_date=datetime(start.year, start.month, start.day, tzinfo=UTC),
            end_date=datetime(end.year, end.month, end.day, 23, 59, 59, tzinfo=UTC),
            status=period_status,
            closed_at=closed_at,
            closed_by=ACTOR_ID if period_status == "hard_closed" else None,
        )
        db.add(p)
        period_ids[name] = p.id
    await db.flush()
    print(f"  [ok] {len(periods_data)} periods (Nov 2025 - Apr 2026)")
    return period_ids


async def seed_contacts(db: AsyncSession) -> dict[str, str]:
    """Create 15 contacts: 8 customers, 5 suppliers, 2 employees."""
    data = [
        # Customers
        ("ABCHOLD", "ABC Holdings Ltd", "customer", "ap@abcholdings.com.hk", "HKD",
         "Unit 1201, Tower 1", None, "Central", "Hong Kong", None, "HK"),
        ("XYZCORP", "XYZ Corporation Ltd", "customer", "accounts@xyzcorp.com.hk", "HKD",
         "Suite 2508, IFC Two", None, "Central", "Hong Kong", None, "HK"),
        ("DEFGRP", "DEF Group Holdings Ltd", "customer", "finance@defgroup.com.hk", "HKD",
         "38/F, Hopewell Centre", None, "Wan Chai", "Hong Kong", None, "HK"),
        ("GHIEDU", "GHI Education Services Ltd", "customer", "billing@ghiedu.com.hk", "HKD",
         "Unit 705, Mira Place", None, "Tsim Sha Tsui", "Kowloon", None, "HK"),
        ("SUNPROP", "Sunrise Properties Ltd", "customer", "accounts@sunriseprop.com.hk", "HKD",
         "Room 1802, China Resources Building", None, "Wan Chai", "Hong Kong", None, "HK"),
        ("MKTTRAD", "MKT Trading Co Ltd", "customer", "invoices@mkttrad.com.hk", "HKD",
         "Unit B, 15/F, Nan Fung Tower", None, "Tsuen Wan", "New Territories", None, "HK"),
        ("GBLTECH", "Global Tech Solutions Inc", "customer", "ar@globaltechsol.com", "USD",
         "350 Fifth Avenue, Suite 4500", None, "New York", "NY", "10118", "US"),
        ("WLCHAN", "W.L. Chan", "customer", "wlchan@gmail.com", "HKD",
         "Flat 12B, Tower 3, The Harbourside", None, "West Kowloon", "Kowloon", None, "HK"),
        # Suppliers
        ("HKLAND", "Henderson Leasing Ltd", "supplier", "leasing@hendersonleasing.com.hk", "HKD",
         "Henderson Centre, 18 Harbour Road", None, "Wan Chai", "Hong Kong", None, "HK"),
        ("CLDSOFT", "CloudSoft Asia Ltd", "supplier", "billing@cloudsoft.asia", "USD",
         "Unit 901, Cyberport 3", None, "Pok Fu Lam", "Hong Kong", None, "HK"),
        ("HKGINS", "Hong Kong General Insurance Co", "supplier", "claims@hkgins.com.hk", "HKD",
         "10/F, Dah Sing Financial Centre", None, "Wan Chai", "Hong Kong", None, "HK"),
        ("OFFMART", "Office Mart Ltd", "supplier", "orders@officemart.com.hk", "HKD",
         "G/F, 88 Des Voeux Road West", None, "Sheung Wan", "Hong Kong", None, "HK"),
        ("WNGTRV", "Wing On Travel Ltd", "supplier", "corporate@wingontravel.com.hk", "HKD",
         "Wing On Centre, 111 Connaught Road", None, "Sheung Wan", "Hong Kong", None, "HK"),
        # Employees
        ("EMPL01", "Kelvin Cheung", "employee", "kelvin.cheung@dragonadvisory.com.hk", "HKD",
         None, None, None, None, None, "HK"),
        ("EMPL02", "Sarah Wong", "employee", "sarah.wong@dragonadvisory.com.hk", "HKD",
         None, None, None, None, None, "HK"),
    ]
    ids: dict[str, str] = {}
    for code, name, ctype, email, ccy, addr1, addr2, city, region, postal, country in data:
        c = Contact(
            id=_uid(),
            tenant_id=TENANT_ID,
            contact_type=ctype,
            name=name,
            code=code,
            email=email,
            currency=ccy,
            address_line1=addr1,
            address_line2=addr2,
            city=city,
            region=region,
            postal_code=postal,
            country=country,
            created_by=ACTOR_ID,
            updated_by=ACTOR_ID,
        )
        db.add(c)
        ids[code] = c.id
    await db.flush()
    print(f"  [ok] {len(data)} contacts (8 customers, 5 suppliers, 2 employees)")
    return ids


async def seed_tax_codes(db: AsyncSession, accs: dict[str, str]) -> dict[str, str]:
    """Create 4 tax codes relevant to Hong Kong."""
    tax_data = [
        {
            "code": "PROFIT",
            "name": "Profits Tax 16.5%",
            "rate": Decimal("0.165000"),
            "tax_type": "output",
            "country": "HK",
            "collected_code": "2200",
        },
        {
            "code": "EXEMPT",
            "name": "Tax Exempt",
            "rate": Decimal("0.000000"),
            "tax_type": "exempt",
            "country": "HK",
            "collected_code": None,
        },
        {
            "code": "ZERO",
            "name": "Zero-rated",
            "rate": Decimal("0.000000"),
            "tax_type": "zero",
            "country": "HK",
            "collected_code": None,
        },
        {
            "code": "NOTAX",
            "name": "No Tax",
            "rate": Decimal("0.000000"),
            "tax_type": "exempt",
            "country": "HK",
            "collected_code": None,
        },
    ]
    ids: dict[str, str] = {}
    for td in tax_data:
        tc = TaxCode(
            id=_uid(),
            tenant_id=TENANT_ID,
            code=td["code"],
            name=td["name"],
            rate=td["rate"],
            tax_type=td["tax_type"],
            country=td["country"],
            tax_collected_account_id=accs[td["collected_code"]] if td["collected_code"] else None,
            is_active=True,
            created_by=ACTOR_ID,
            updated_by=ACTOR_ID,
        )
        db.add(tc)
        ids[td["code"]] = tc.id
    await db.flush()
    print(f"  [ok] {len(tax_data)} tax codes")
    return ids


async def seed_items(db: AsyncSession, accs: dict[str, str]) -> dict[str, str]:
    """Create 5 service items."""
    items_data = [
        {
            "code": "CONSULT",
            "name": "Consulting Services",
            "item_type": "service",
            "unit": "hour",
            "sales_price": Decimal("2500.0000"),
            "sales_account": "4000",
        },
        {
            "code": "AUDIT",
            "name": "Audit Services",
            "item_type": "service",
            "unit": "hour",
            "sales_price": Decimal("2200.0000"),
            "sales_account": "4100",
        },
        {
            "code": "TAXADV",
            "name": "Tax Advisory Services",
            "item_type": "service",
            "unit": "hour",
            "sales_price": Decimal("2800.0000"),
            "sales_account": "4200",
        },
        {
            "code": "TRAIN",
            "name": "Training & Workshop",
            "item_type": "service",
            "unit": "day",
            "sales_price": Decimal("15000.0000"),
            "sales_account": "4300",
        },
        {
            "code": "DISB",
            "name": "Disbursements",
            "item_type": "service",
            "unit": "unit",
            "sales_price": Decimal("1.0000"),
            "sales_account": "4400",
        },
    ]
    ids: dict[str, str] = {}
    for it in items_data:
        item = Item(
            id=_uid(),
            tenant_id=TENANT_ID,
            code=it["code"],
            name=it["name"],
            item_type=it["item_type"],
            unit_of_measure=it["unit"],
            sales_unit_price=it["sales_price"],
            currency="HKD",
            sales_account_id=accs[it["sales_account"]],
            created_by=ACTOR_ID,
            updated_by=ACTOR_ID,
        )
        db.add(item)
        ids[it["code"]] = item.id
    await db.flush()
    print(f"  [ok] {len(items_data)} items")
    return ids


async def seed_fx_rates(db: AsyncSession) -> None:
    """Create 6 months of USD/HKD and GBP/HKD rates."""
    # Realistic rates with slight monthly variation
    usd_hkd_rates = [
        ("2025-11-01", Decimal("7.80120000")),
        ("2025-12-01", Decimal("7.80450000")),
        ("2026-01-01", Decimal("7.79800000")),
        ("2026-02-01", Decimal("7.80600000")),
        ("2026-03-01", Decimal("7.81000000")),
        ("2026-04-01", Decimal("7.79500000")),
    ]
    gbp_hkd_rates = [
        ("2025-11-01", Decimal("9.85200000")),
        ("2025-12-01", Decimal("9.90100000")),
        ("2026-01-01", Decimal("9.88500000")),
        ("2026-02-01", Decimal("9.92300000")),
        ("2026-03-01", Decimal("9.95000000")),
        ("2026-04-01", Decimal("9.87600000")),
    ]
    count = 0
    for rate_date, rate in usd_hkd_rates:
        db.add(FxRate(
            id=_uid(),
            from_currency="USD",
            to_currency="HKD",
            rate_date=_dt(rate_date),
            rate=rate,
            source="manual",
        ))
        count += 1
    for rate_date, rate in gbp_hkd_rates:
        db.add(FxRate(
            id=_uid(),
            from_currency="GBP",
            to_currency="HKD",
            rate_date=_dt(rate_date),
            rate=rate,
            source="manual",
        ))
        count += 1
    await db.flush()
    print(f"  [ok] {count} FX rates (USD/HKD + GBP/HKD)")


def _make_je(
    number: str,
    desc: str,
    txn_date: str,
    period_id: str,
    lines: list[dict],
    currency: str = "HKD",
    source_type: str = "manual",
) -> tuple[JournalEntry, list[JournalLine]]:
    """Helper to create a journal entry with lines."""
    txn_dt = _dt(txn_date)
    total_debit = sum(Decimal(ln["debit"]) for ln in lines)
    total_credit = sum(Decimal(ln["credit"]) for ln in lines)
    je = JournalEntry(
        id=_uid(),
        tenant_id=TENANT_ID,
        number=number,
        status="posted",
        description=desc,
        date=txn_dt,
        period_id=period_id,
        currency=currency,
        source_type=source_type,
        total_debit=total_debit,
        total_credit=total_credit,
        posted_at=txn_dt,
        posted_by=ACTOR_ID,
        created_by=ACTOR_ID,
        updated_by=ACTOR_ID,
    )
    jls = []
    for i, ln in enumerate(lines, 1):
        fx = Decimal(ln.get("fx_rate", "1"))
        debit = Decimal(ln["debit"])
        credit = Decimal(ln["credit"])
        jls.append(
            JournalLine(
                id=_uid(),
                tenant_id=TENANT_ID,
                journal_entry_id=je.id,
                line_no=i,
                account_id=ln["account_id"],
                description=ln.get("desc"),
                debit=debit,
                credit=credit,
                currency=ln.get("currency", currency),
                fx_rate=fx,
                functional_debit=debit * fx if currency != "HKD" else debit,
                functional_credit=credit * fx if currency != "HKD" else credit,
            )
        )
    return je, jls


async def seed_journals(
    db: AsyncSession,
    accs: dict[str, str],
    periods: dict[str, str],
) -> dict[str, str]:
    """Create 20 posted journal entries across all periods."""
    entries = [
        # --- Nov 2025 ---
        ("JE-00001", "Opening balances — initial capital injection",
         "2025-11-01", "2025-11", [
             {"account_id": accs["1000"], "debit": "2000000.0000", "credit": "0.0000", "desc": "Cash at Bank HKD"},
             {"account_id": accs["1010"], "debit": "500000.0000", "credit": "0.0000", "desc": "Cash at Bank USD"},
             {"account_id": accs["1500"], "debit": "120000.0000", "credit": "0.0000", "desc": "Office Equipment"},
             {"account_id": accs["1510"], "debit": "85000.0000", "credit": "0.0000", "desc": "Computer Equipment"},
             {"account_id": accs["1520"], "debit": "350000.0000", "credit": "0.0000", "desc": "Leasehold Improvements"},
             {"account_id": accs["3000"], "debit": "0.0000", "credit": "1000000.0000", "desc": "Share Capital"},
             {"account_id": accs["3100"], "debit": "0.0000", "credit": "2055000.0000", "desc": "Retained Earnings"},
         ]),
        ("JE-00002", "Nov 2025 salary accrual — all staff",
         "2025-11-30", "2025-11", [
             {"account_id": accs["5000"], "debit": "280000.0000", "credit": "0.0000", "desc": "Salaries Nov"},
             {"account_id": accs["5100"], "debit": "14000.0000", "credit": "0.0000", "desc": "MPF employer Nov"},
             {"account_id": accs["1000"], "debit": "0.0000", "credit": "266000.0000", "desc": "Net salary paid"},
             {"account_id": accs["2300"], "debit": "0.0000", "credit": "28000.0000", "desc": "MPF payable (employer+employee)"},
         ]),
        ("JE-00003", "Nov 2025 office rent",
         "2025-11-01", "2025-11", [
             {"account_id": accs["6000"], "debit": "65000.0000", "credit": "0.0000", "desc": "Rent — November"},
             {"account_id": accs["1000"], "debit": "0.0000", "credit": "65000.0000"},
         ]),
        ("JE-00004", "Nov 2025 depreciation",
         "2025-11-30", "2025-11", [
             {"account_id": accs["6700"], "debit": "6250.0000", "credit": "0.0000", "desc": "Monthly depreciation"},
             {"account_id": accs["1550"], "debit": "0.0000", "credit": "2000.0000", "desc": "Office equip depr"},
             {"account_id": accs["1560"], "debit": "0.0000", "credit": "1416.6700", "desc": "Computer equip depr"},
             {"account_id": accs["1570"], "debit": "0.0000", "credit": "2833.3300", "desc": "Leasehold impr depr"},
         ]),
        # --- Dec 2025 ---
        ("JE-00005", "Dec 2025 salary accrual",
         "2025-12-31", "2025-12", [
             {"account_id": accs["5000"], "debit": "280000.0000", "credit": "0.0000"},
             {"account_id": accs["5100"], "debit": "14000.0000", "credit": "0.0000"},
             {"account_id": accs["1000"], "debit": "0.0000", "credit": "266000.0000"},
             {"account_id": accs["2300"], "debit": "0.0000", "credit": "28000.0000"},
         ]),
        ("JE-00006", "Dec 2025 office rent",
         "2025-12-01", "2025-12", [
             {"account_id": accs["6000"], "debit": "65000.0000", "credit": "0.0000"},
             {"account_id": accs["1000"], "debit": "0.0000", "credit": "65000.0000"},
         ]),
        ("JE-00007", "Dec 2025 depreciation",
         "2025-12-31", "2025-12", [
             {"account_id": accs["6700"], "debit": "6250.0000", "credit": "0.0000"},
             {"account_id": accs["1550"], "debit": "0.0000", "credit": "2000.0000"},
             {"account_id": accs["1560"], "debit": "0.0000", "credit": "1416.6700"},
             {"account_id": accs["1570"], "debit": "0.0000", "credit": "2833.3300"},
         ]),
        ("JE-00008", "Dec 2025 year-end FX revaluation — USD account",
         "2025-12-31", "2025-12", [
             {"account_id": accs["1010"], "debit": "2250.0000", "credit": "0.0000", "desc": "USD revaluation gain"},
             {"account_id": accs["4910"], "debit": "0.0000", "credit": "2250.0000", "desc": "FX gain"},
         ]),
        # --- Jan 2026 ---
        ("JE-00009", "Jan 2026 salary accrual",
         "2026-01-31", "2026-01", [
             {"account_id": accs["5000"], "debit": "280000.0000", "credit": "0.0000"},
             {"account_id": accs["5100"], "debit": "14000.0000", "credit": "0.0000"},
             {"account_id": accs["1000"], "debit": "0.0000", "credit": "266000.0000"},
             {"account_id": accs["2300"], "debit": "0.0000", "credit": "28000.0000"},
         ]),
        ("JE-00010", "Jan 2026 office rent",
         "2026-01-01", "2026-01", [
             {"account_id": accs["6000"], "debit": "65000.0000", "credit": "0.0000"},
             {"account_id": accs["1000"], "debit": "0.0000", "credit": "65000.0000"},
         ]),
        ("JE-00011", "Jan 2026 depreciation",
         "2026-01-31", "2026-01", [
             {"account_id": accs["6700"], "debit": "6250.0000", "credit": "0.0000"},
             {"account_id": accs["1550"], "debit": "0.0000", "credit": "2000.0000"},
             {"account_id": accs["1560"], "debit": "0.0000", "credit": "1416.6700"},
             {"account_id": accs["1570"], "debit": "0.0000", "credit": "2833.3300"},
         ]),
        ("JE-00012", "Jan 2026 insurance prepayment (annual policy)",
         "2026-01-15", "2026-01", [
             {"account_id": accs["1200"], "debit": "36000.0000", "credit": "0.0000", "desc": "Annual insurance prepaid"},
             {"account_id": accs["1000"], "debit": "0.0000", "credit": "36000.0000"},
         ]),
        # --- Feb 2026 ---
        ("JE-00013", "Feb 2026 salary accrual",
         "2026-02-28", "2026-02", [
             {"account_id": accs["5000"], "debit": "280000.0000", "credit": "0.0000"},
             {"account_id": accs["5100"], "debit": "14000.0000", "credit": "0.0000"},
             {"account_id": accs["1000"], "debit": "0.0000", "credit": "266000.0000"},
             {"account_id": accs["2300"], "debit": "0.0000", "credit": "28000.0000"},
         ]),
        ("JE-00014", "Feb 2026 office rent",
         "2026-02-01", "2026-02", [
             {"account_id": accs["6000"], "debit": "65000.0000", "credit": "0.0000"},
             {"account_id": accs["1000"], "debit": "0.0000", "credit": "65000.0000"},
         ]),
        ("JE-00015", "Feb 2026 depreciation + insurance amortization",
         "2026-02-28", "2026-02", [
             {"account_id": accs["6700"], "debit": "6250.0000", "credit": "0.0000"},
             {"account_id": accs["1550"], "debit": "0.0000", "credit": "2000.0000"},
             {"account_id": accs["1560"], "debit": "0.0000", "credit": "1416.6700"},
             {"account_id": accs["1570"], "debit": "0.0000", "credit": "2833.3300"},
         ]),
        ("JE-00016", "Feb 2026 insurance amortization (1/12 of annual)",
         "2026-02-28", "2026-02", [
             {"account_id": accs["6200"], "debit": "3000.0000", "credit": "0.0000", "desc": "Monthly insurance"},
             {"account_id": accs["1200"], "debit": "0.0000", "credit": "3000.0000"},
         ]),
        # --- Mar 2026 ---
        ("JE-00017", "Mar 2026 salary accrual",
         "2026-03-31", "2026-03", [
             {"account_id": accs["5000"], "debit": "280000.0000", "credit": "0.0000"},
             {"account_id": accs["5100"], "debit": "14000.0000", "credit": "0.0000"},
             {"account_id": accs["1000"], "debit": "0.0000", "credit": "266000.0000"},
             {"account_id": accs["2300"], "debit": "0.0000", "credit": "28000.0000"},
         ]),
        ("JE-00018", "Mar 2026 office rent",
         "2026-03-01", "2026-03", [
             {"account_id": accs["6000"], "debit": "65000.0000", "credit": "0.0000"},
             {"account_id": accs["1000"], "debit": "0.0000", "credit": "65000.0000"},
         ]),
        ("JE-00019", "Mar 2026 depreciation",
         "2026-03-31", "2026-03", [
             {"account_id": accs["6700"], "debit": "6250.0000", "credit": "0.0000"},
             {"account_id": accs["1550"], "debit": "0.0000", "credit": "2000.0000"},
             {"account_id": accs["1560"], "debit": "0.0000", "credit": "1416.6700"},
             {"account_id": accs["1570"], "debit": "0.0000", "credit": "2833.3300"},
         ]),
        # --- Apr 2026 ---
        ("JE-00020", "Apr 2026 office rent",
         "2026-04-01", "2026-04", [
             {"account_id": accs["6000"], "debit": "65000.0000", "credit": "0.0000"},
             {"account_id": accs["1000"], "debit": "0.0000", "credit": "65000.0000"},
         ]),
    ]

    je_ids: dict[str, str] = {}
    for number, desc, txn_date, period_name, lines in entries:
        if period_name not in periods:
            print(f"  [warn] Skipping JE {number} -- period {period_name} not found")
            continue
        je, jls = _make_je(number, desc, txn_date, periods[period_name], lines)
        db.add(je)
        for jl in jls:
            db.add(jl)
        je_ids[number] = je.id

    await db.flush()
    print(f"  [ok] {len(je_ids)} journal entries")
    return je_ids


async def seed_invoices(
    db: AsyncSession,
    accs: dict[str, str],
    contacts: dict[str, str],
    items: dict[str, str],
) -> dict[str, str]:
    """Create 14 invoices with varying statuses."""
    # (number, contact, issue_date, due_date, period, currency, fx_rate, lines, status)
    # lines: [(desc, qty, unit_price, account_code)]
    data = [
        # Paid invoices
        ("INV-00001", "ABCHOLD", "2025-11-15", "2025-12-15", "2025-11", "HKD", "1",
         [("Consulting — corporate restructuring Nov", Decimal("40"), Decimal("2500.0000"), "4000")],
         "paid"),
        ("INV-00002", "XYZCORP", "2025-12-01", "2025-12-31", "2025-12", "HKD", "1",
         [("Audit services — FY2025 interim", Decimal("60"), Decimal("2200.0000"), "4100"),
          ("Disbursements — government filing fees", Decimal("1"), Decimal("2500.0000"), "4400")],
         "paid"),
        ("INV-00003", "DEFGRP", "2026-01-10", "2026-02-10", "2026-01", "HKD", "1",
         [("Tax advisory — group restructuring", Decimal("30"), Decimal("2800.0000"), "4200")],
         "paid"),
        ("INV-00004", "SUNPROP", "2026-01-20", "2026-02-20", "2026-01", "HKD", "1",
         [("Consulting — property acquisition due diligence", Decimal("25"), Decimal("2500.0000"), "4000")],
         "paid"),
        # Partially paid
        ("INV-00005", "MKTTRAD", "2026-02-01", "2026-03-03", "2026-02", "HKD", "1",
         [("Tax advisory — transfer pricing study", Decimal("50"), Decimal("2800.0000"), "4200"),
          ("Disbursements — HKICPA filing", Decimal("1"), Decimal("3800.0000"), "4400")],
         "partial"),
        # Authorised (approved, not yet sent)
        ("INV-00006", "ABCHOLD", "2026-03-01", "2026-03-31", "2026-03", "HKD", "1",
         [("Consulting — Q1 2026 retainer", Decimal("80"), Decimal("2500.0000"), "4000")],
         "authorised"),
        ("INV-00007", "DEFGRP", "2026-03-15", "2026-04-14", "2026-03", "HKD", "1",
         [("Audit services — FY2025 final audit", Decimal("120"), Decimal("2200.0000"), "4100"),
          ("Disbursements — travel to Shenzhen", Decimal("1"), Decimal("4500.0000"), "4400")],
         "authorised"),
        ("INV-00008", "GHIEDU", "2026-03-20", "2026-04-19", "2026-03", "HKD", "1",
         [("Training — Financial Reporting Standards workshop (2 days)", Decimal("2"), Decimal("15000.0000"), "4300")],
         "authorised"),
        # Sent
        ("INV-00009", "SUNPROP", "2026-04-01", "2026-05-01", "2026-04", "HKD", "1",
         [("Consulting — lease renewal advisory", Decimal("15"), Decimal("2500.0000"), "4000")],
         "sent"),
        ("INV-00010", "WLCHAN", "2026-04-05", "2026-05-05", "2026-04", "HKD", "1",
         [("Tax advisory — personal tax return FY2025/26", Decimal("8"), Decimal("2800.0000"), "4200")],
         "sent"),
        # Draft
        ("INV-00011", "MKTTRAD", "2026-04-10", None, "2026-04", "HKD", "1",
         [("Consulting — supply chain review", Decimal("20"), Decimal("2500.0000"), "4000")],
         "draft"),
        ("INV-00012", "XYZCORP", "2026-04-12", None, "2026-04", "HKD", "1",
         [("Audit services — interim review Q1 2026", Decimal("35"), Decimal("2200.0000"), "4100")],
         "draft"),
        # USD invoice (international client)
        ("INV-00013", "GBLTECH", "2026-03-01", "2026-04-01", "2026-03", "USD", "7.81000000",
         [("Consulting — APAC market entry strategy", Decimal("60"), Decimal("350.0000"), "4000"),
          ("Tax advisory — HK tax structuring", Decimal("20"), Decimal("400.0000"), "4200")],
         "authorised"),
        # Another paid HKD
        ("INV-00014", "GHIEDU", "2025-12-10", "2026-01-10", "2025-12", "HKD", "1",
         [("Training — Corporate Governance workshop (1 day)", Decimal("1"), Decimal("15000.0000"), "4300")],
         "paid"),
    ]

    inv_ids: dict[str, str] = {}
    for number, contact_code, issue, due, period, ccy, fx, lines_data, inv_status in data:
        subtotal = sum(qty * price for _, qty, price, _ in lines_data)
        total = subtotal
        fx_rate = Decimal(fx)
        functional_total = total * fx_rate if ccy != "HKD" else total

        if inv_status == "paid":
            amount_due = Decimal("0.0000")
        elif inv_status == "partial":
            # Simulate 50% paid for partial
            amount_due = total / 2
        else:
            amount_due = total

        inv_id = _uid()
        inv = Invoice(
            id=inv_id,
            tenant_id=TENANT_ID,
            number=number,
            status=inv_status,
            contact_id=contacts[contact_code],
            issue_date=issue,
            due_date=due,
            period_name=period,
            currency=ccy,
            fx_rate=fx_rate,
            subtotal=subtotal,
            tax_total=Decimal("0.0000"),
            total=total,
            amount_due=amount_due,
            functional_total=functional_total,
            authorised_by=ACTOR_ID if inv_status in ("authorised", "sent", "paid", "partial") else None,
            sent_at=_now() if inv_status in ("sent", "paid", "partial") else None,
            paid_at=_now() if inv_status == "paid" else None,
            created_by=ACTOR_ID,
            updated_by=ACTOR_ID,
        )
        db.add(inv)

        for i, (desc, qty, price, acc_code) in enumerate(lines_data, 1):
            line_amt = qty * price
            il = InvoiceLine(
                id=_uid(),
                tenant_id=TENANT_ID,
                invoice_id=inv_id,
                line_no=i,
                account_id=accs[acc_code],
                description=desc,
                quantity=qty,
                unit_price=price,
                discount_pct=Decimal("0.0000"),
                line_amount=line_amt,
                tax_amount=Decimal("0.0000"),
            )
            db.add(il)
        inv_ids[number] = inv_id

    await db.flush()
    print(f"  [ok] {len(data)} invoices")
    return inv_ids


async def seed_bills(
    db: AsyncSession,
    accs: dict[str, str],
    contacts: dict[str, str],
) -> dict[str, str]:
    """Create 12 bills with varying statuses."""
    data = [
        # Paid rent bills (Nov-Feb)
        ("BILL-00001", "HKLAND", "2025-11-01", "2025-11-15", "2025-11", "6000",
         "Office rent — November 2025", Decimal("65000.0000"), "paid", "HKD", "1"),
        ("BILL-00002", "HKLAND", "2025-12-01", "2025-12-15", "2025-12", "6000",
         "Office rent — December 2025", Decimal("65000.0000"), "paid", "HKD", "1"),
        ("BILL-00003", "HKLAND", "2026-01-01", "2026-01-15", "2026-01", "6000",
         "Office rent — January 2026", Decimal("65000.0000"), "paid", "HKD", "1"),
        ("BILL-00004", "HKLAND", "2026-02-01", "2026-02-15", "2026-02", "6000",
         "Office rent — February 2026", Decimal("65000.0000"), "paid", "HKD", "1"),
        # Software subscription (USD supplier)
        ("BILL-00005", "CLDSOFT", "2025-12-01", "2025-12-31", "2025-12", "6600",
         "CloudSoft Enterprise Suite — Dec 2025", Decimal("1200.0000"), "paid", "USD", "7.80450000"),
        ("BILL-00006", "CLDSOFT", "2026-01-01", "2026-01-31", "2026-01", "6600",
         "CloudSoft Enterprise Suite — Jan 2026", Decimal("1200.0000"), "paid", "USD", "7.79800000"),
        # Insurance annual premium
        ("BILL-00007", "HKGINS", "2026-01-15", "2026-02-15", "2026-01", "6200",
         "Professional indemnity insurance — annual premium FY2026", Decimal("36000.0000"), "paid", "HKD", "1"),
        # Approved but not yet paid
        ("BILL-00008", "HKLAND", "2026-03-01", "2026-03-15", "2026-03", "6000",
         "Office rent — March 2026", Decimal("65000.0000"), "approved", "HKD", "1"),
        ("BILL-00009", "OFFMART", "2026-03-10", "2026-04-10", "2026-03", "6900",
         "Stationery and printing supplies Q1 2026", Decimal("4800.0000"), "approved", "HKD", "1"),
        ("BILL-00010", "CLDSOFT", "2026-03-01", "2026-03-31", "2026-03", "6600",
         "CloudSoft Enterprise Suite — Mar 2026", Decimal("1200.0000"), "approved", "USD", "7.81000000"),
        # Draft bills
        ("BILL-00011", "HKLAND", "2026-04-01", "2026-04-15", "2026-04", "6000",
         "Office rent — April 2026", Decimal("65000.0000"), "draft", "HKD", "1"),
        ("BILL-00012", "WNGTRV", "2026-04-05", "2026-05-05", "2026-04", "6300",
         "Business travel — Shenzhen site visit", Decimal("8500.0000"), "draft", "HKD", "1"),
    ]

    bill_ids: dict[str, str] = {}
    for number, contact_code, issue, due, period, exp_code, desc, amount, bill_status, ccy, fx in data:
        amt = amount
        fx_rate = Decimal(fx)
        functional_total = amt * fx_rate if ccy != "HKD" else amt
        amount_due = Decimal("0.0000") if bill_status == "paid" else amt
        bill_id = _uid()
        bill = Bill(
            id=bill_id,
            tenant_id=TENANT_ID,
            number=number,
            status=bill_status,
            contact_id=contacts[contact_code],
            issue_date=issue,
            due_date=due,
            period_name=period,
            currency=ccy,
            fx_rate=fx_rate,
            subtotal=amt,
            tax_total=Decimal("0.0000"),
            total=amt,
            amount_due=amount_due,
            functional_total=functional_total,
            approved_by=ACTOR_ID if bill_status in ("approved", "paid") else None,
            approved_at=_now() if bill_status in ("approved", "paid") else None,
            created_by=ACTOR_ID,
            updated_by=ACTOR_ID,
        )
        db.add(bill)
        bl = BillLine(
            id=_uid(),
            tenant_id=TENANT_ID,
            bill_id=bill_id,
            line_no=1,
            account_id=accs[exp_code],
            description=desc,
            quantity=Decimal("1.0000"),
            unit_price=amt,
            discount_pct=Decimal("0.0000"),
            line_amount=amt,
            tax_amount=Decimal("0.0000"),
        )
        db.add(bl)
        bill_ids[number] = bill_id

    await db.flush()
    print(f"  [ok] {len(data)} bills")
    return bill_ids


async def seed_payments(
    db: AsyncSession,
    accs: dict[str, str],
    contacts: dict[str, str],
    inv_ids: dict[str, str],
    bill_ids: dict[str, str],
) -> None:
    """Create 10 payments: 6 received from customers, 4 made to suppliers."""
    received = [
        # Full payment of INV-00001 (HK$100,000)
        ("PAY-R001", "ABCHOLD", "2025-12-10", Decimal("100000.0000"), "HKD", "1",
         "HSBC TT ref: TT-20251210-001", "INV-00001"),
        # Full payment of INV-00002 (HK$134,500)
        ("PAY-R002", "XYZCORP", "2025-12-28", Decimal("134500.0000"), "HKD", "1",
         "BOC cheque #882401", "INV-00002"),
        # Full payment of INV-00003 (HK$84,000)
        ("PAY-R003", "DEFGRP", "2026-02-05", Decimal("84000.0000"), "HKD", "1",
         "HSBC TT ref: TT-20260205-003", "INV-00003"),
        # Full payment of INV-00004 (HK$62,500)
        ("PAY-R004", "SUNPROP", "2026-02-18", Decimal("62500.0000"), "HKD", "1",
         "DBS transfer ref: DBS-0218-SP", "INV-00004"),
        # Full payment of INV-00014 (HK$15,000)
        ("PAY-R005", "GHIEDU", "2026-01-08", Decimal("15000.0000"), "HKD", "1",
         "Cheque #GHI-20260108", "INV-00014"),
        # Partial payment of INV-00005 (50% of HK$143,800)
        ("PAY-R006", "MKTTRAD", "2026-03-01", Decimal("71900.0000"), "HKD", "1",
         "MKT bank transfer partial", "INV-00005"),
    ]

    for number, contact_code, pay_date, amount, ccy, fx, ref, inv_num in received:
        payment_id = _uid()
        fx_rate = Decimal(fx)
        payment = Payment(
            id=payment_id,
            tenant_id=TENANT_ID,
            number=number,
            payment_type="received",
            status="applied",
            contact_id=contacts[contact_code],
            payment_date=pay_date,
            amount=amount,
            currency=ccy,
            fx_rate=fx_rate,
            functional_amount=amount * fx_rate if ccy != "HKD" else amount,
            reference=ref,
            created_by=ACTOR_ID,
            updated_by=ACTOR_ID,
        )
        db.add(payment)
        alloc = PaymentAllocation(
            id=_uid(),
            tenant_id=TENANT_ID,
            payment_id=payment_id,
            invoice_id=inv_ids[inv_num],
            bill_id=None,
            amount=amount,
            currency=ccy,
            created_by=ACTOR_ID,
        )
        db.add(alloc)

    # Supplier payments
    made = [
        # Rent payments
        ("PAY-M001", "HKLAND", "2025-11-05", Decimal("65000.0000"), "HKD", "1",
         "Autopay — rent Nov 2025", "BILL-00001"),
        ("PAY-M002", "HKLAND", "2025-12-05", Decimal("65000.0000"), "HKD", "1",
         "Autopay — rent Dec 2025", "BILL-00002"),
        ("PAY-M003", "HKLAND", "2026-01-05", Decimal("65000.0000"), "HKD", "1",
         "Autopay — rent Jan 2026", "BILL-00003"),
        ("PAY-M004", "HKLAND", "2026-02-05", Decimal("65000.0000"), "HKD", "1",
         "Autopay — rent Feb 2026", "BILL-00004"),
    ]

    for number, contact_code, pay_date, amount, ccy, fx, ref, bill_num in made:
        payment_id = _uid()
        fx_rate = Decimal(fx)
        payment = Payment(
            id=payment_id,
            tenant_id=TENANT_ID,
            number=number,
            payment_type="made",
            status="applied",
            contact_id=contacts[contact_code],
            payment_date=pay_date,
            amount=amount,
            currency=ccy,
            fx_rate=fx_rate,
            functional_amount=amount * fx_rate if ccy != "HKD" else amount,
            reference=ref,
            created_by=ACTOR_ID,
            updated_by=ACTOR_ID,
        )
        db.add(payment)
        alloc = PaymentAllocation(
            id=_uid(),
            tenant_id=TENANT_ID,
            payment_id=payment_id,
            invoice_id=None,
            bill_id=bill_ids[bill_num],
            amount=amount,
            currency=ccy,
            created_by=ACTOR_ID,
        )
        db.add(alloc)

    await db.flush()
    total = len(received) + len(made)
    print(f"  [ok] {total} payments ({len(received)} received, {len(made)} made)")


async def seed_bank_accounts(
    db: AsyncSession,
    accs: dict[str, str],
) -> dict[str, str]:
    """Create 2 bank accounts: HKD operating + USD account."""
    ba_hkd = BankAccount(
        id=_uid(),
        tenant_id=TENANT_ID,
        name="Dragon Advisory — HSBC HKD Operating",
        bank_name="HSBC Hong Kong",
        account_number="****8012",
        currency="HKD",
        coa_account_id=accs["1000"],
        is_active=True,
        created_by=ACTOR_ID,
        updated_by=ACTOR_ID,
    )
    db.add(ba_hkd)

    ba_usd = BankAccount(
        id=_uid(),
        tenant_id=TENANT_ID,
        name="Dragon Advisory — HSBC USD",
        bank_name="HSBC Hong Kong",
        account_number="****8013",
        currency="USD",
        coa_account_id=accs["1010"],
        is_active=True,
        created_by=ACTOR_ID,
        updated_by=ACTOR_ID,
    )
    db.add(ba_usd)
    await db.flush()
    print("  [ok] 2 bank accounts (HKD + USD)")
    return {"HKD": ba_hkd.id, "USD": ba_usd.id}


async def seed_bank_transactions(
    db: AsyncSession,
    bank_accounts: dict[str, str],
) -> None:
    """Create 35+ HKD transactions and 10 USD transactions."""
    hkd_ba = bank_accounts["HKD"]
    usd_ba = bank_accounts["USD"]

    hkd_txns = [
        # Nov 2025
        (_d("2025-11-05"), "Autopay — Henderson Leasing rent", Decimal("-65000.0000"), "RENT-NOV25", True),
        (_d("2025-11-15"), "HSBC payroll batch Nov", Decimal("-266000.0000"), "PAYROLL-NOV25", True),
        (_d("2025-11-20"), "MPF remittance — Nov", Decimal("-28000.0000"), "MPF-NOV25", True),
        (_d("2025-11-25"), "Bank charges — Nov", Decimal("-350.0000"), "BC-NOV25", True),
        # Dec 2025
        (_d("2025-12-05"), "Autopay — Henderson Leasing rent", Decimal("-65000.0000"), "RENT-DEC25", True),
        (_d("2025-12-10"), "TT from ABC Holdings Ltd", Decimal("100000.0000"), "TT-20251210-001", True),
        (_d("2025-12-15"), "HSBC payroll batch Dec", Decimal("-266000.0000"), "PAYROLL-DEC25", True),
        (_d("2025-12-20"), "MPF remittance — Dec", Decimal("-28000.0000"), "MPF-DEC25", True),
        (_d("2025-12-28"), "BOC cheque deposit — XYZ Corporation", Decimal("134500.0000"), "CHQ-882401", True),
        (_d("2025-12-30"), "Bank charges — Dec", Decimal("-420.0000"), "BC-DEC25", True),
        # Jan 2026
        (_d("2026-01-05"), "Autopay — Henderson Leasing rent", Decimal("-65000.0000"), "RENT-JAN26", True),
        (_d("2026-01-08"), "Cheque deposit — GHI Education", Decimal("15000.0000"), "CHQ-GHI-0108", True),
        (_d("2026-01-15"), "HSBC payroll batch Jan", Decimal("-266000.0000"), "PAYROLL-JAN26", True),
        (_d("2026-01-15"), "Insurance premium — HK General Insurance", Decimal("-36000.0000"), "INS-FY26", True),
        (_d("2026-01-20"), "MPF remittance — Jan", Decimal("-28000.0000"), "MPF-JAN26", True),
        (_d("2026-01-30"), "Bank charges — Jan", Decimal("-380.0000"), "BC-JAN26", True),
        # Feb 2026
        (_d("2026-02-05"), "Autopay — Henderson Leasing rent", Decimal("-65000.0000"), "RENT-FEB26", True),
        (_d("2026-02-05"), "TT from DEF Group Holdings", Decimal("84000.0000"), "TT-20260205-003", True),
        (_d("2026-02-15"), "HSBC payroll batch Feb", Decimal("-266000.0000"), "PAYROLL-FEB26", True),
        (_d("2026-02-18"), "DBS transfer from Sunrise Properties", Decimal("62500.0000"), "DBS-0218-SP", True),
        (_d("2026-02-20"), "MPF remittance — Feb", Decimal("-28000.0000"), "MPF-FEB26", True),
        (_d("2026-02-28"), "Bank charges — Feb", Decimal("-390.0000"), "BC-FEB26", True),
        # Mar 2026
        (_d("2026-03-01"), "MKT Trading partial payment", Decimal("71900.0000"), "MKT-PART-0301", True),
        (_d("2026-03-05"), "Autopay — Henderson Leasing rent", Decimal("-65000.0000"), "RENT-MAR26", False),
        (_d("2026-03-10"), "Office Mart — stationery", Decimal("-4800.0000"), "OFFMART-Q1", False),
        (_d("2026-03-15"), "HSBC payroll batch Mar", Decimal("-266000.0000"), "PAYROLL-MAR26", False),
        (_d("2026-03-20"), "MPF remittance — Mar", Decimal("-28000.0000"), "MPF-MAR26", False),
        (_d("2026-03-25"), "Telephone & internet — PCCW", Decimal("-1850.0000"), "PCCW-MAR26", False),
        (_d("2026-03-28"), "Cleaning service — monthly", Decimal("-3200.0000"), "CLEAN-MAR26", False),
        (_d("2026-03-31"), "Bank charges — Mar", Decimal("-410.0000"), "BC-MAR26", False),
        # Apr 2026 (current month — all unreconciled)
        (_d("2026-04-01"), "Autopay — Henderson Leasing rent", Decimal("-65000.0000"), "RENT-APR26", False),
        (_d("2026-04-05"), "Wing On Travel — Shenzhen trip", Decimal("-8500.0000"), "WNGTRV-SZ", False),
        (_d("2026-04-10"), "Incoming transfer — pending match", Decimal("25000.0000"), "UNKNOWN-0410", False),
        (_d("2026-04-12"), "Card purchase — restaurant client dinner", Decimal("-2800.0000"), "CARD-0412", False),
        (_d("2026-04-15"), "HSBC payroll batch Apr", Decimal("-266000.0000"), "PAYROLL-APR26", False),
    ]

    for txn_date, desc, amount, ref, reconciled in hkd_txns:
        txn = BankTransaction(
            id=_uid(),
            tenant_id=TENANT_ID,
            bank_account_id=hkd_ba,
            transaction_date=txn_date,
            description=desc,
            reference=ref,
            amount=amount,
            currency="HKD",
            is_reconciled=reconciled,
            reconciled_at=_now() if reconciled else None,
            created_by=ACTOR_ID,
            updated_by=ACTOR_ID,
        )
        db.add(txn)

    usd_txns = [
        (_d("2025-12-01"), "CloudSoft subscription — Dec", Decimal("-1200.0000"), "CLDSOFT-DEC25", True),
        (_d("2025-12-15"), "Wire from Global Tech Solutions", Decimal("5000.0000"), "GBLTECH-DEC25", True),
        (_d("2026-01-01"), "CloudSoft subscription — Jan", Decimal("-1200.0000"), "CLDSOFT-JAN26", True),
        (_d("2026-02-01"), "CloudSoft subscription — Feb", Decimal("-1200.0000"), "CLDSOFT-FEB26", True),
        (_d("2026-03-01"), "CloudSoft subscription — Mar", Decimal("-1200.0000"), "CLDSOFT-MAR26", False),
        (_d("2026-03-15"), "Wire from Global Tech Solutions", Decimal("29000.0000"), "GBLTECH-MAR26", False),
        (_d("2026-03-31"), "Bank charges — USD Mar", Decimal("-25.0000"), "BC-USD-MAR26", False),
        (_d("2026-04-01"), "CloudSoft subscription — Apr", Decimal("-1200.0000"), "CLDSOFT-APR26", False),
        (_d("2026-04-10"), "Incoming wire — pending", Decimal("8000.0000"), "UNKNOWN-USD-0410", False),
        (_d("2026-04-15"), "Bank charges — USD Apr", Decimal("-25.0000"), "BC-USD-APR26", False),
    ]

    for txn_date, desc, amount, ref, reconciled in usd_txns:
        txn = BankTransaction(
            id=_uid(),
            tenant_id=TENANT_ID,
            bank_account_id=usd_ba,
            transaction_date=txn_date,
            description=desc,
            reference=ref,
            amount=amount,
            currency="USD",
            is_reconciled=reconciled,
            reconciled_at=_now() if reconciled else None,
            created_by=ACTOR_ID,
            updated_by=ACTOR_ID,
        )
        db.add(txn)

    await db.flush()
    print(f"  [ok] {len(hkd_txns)} HKD + {len(usd_txns)} USD bank transactions")


async def seed_expense_claims(
    db: AsyncSession,
    accs: dict[str, str],
    contacts: dict[str, str],
) -> None:
    """Create 3 expense claims for employees."""
    claims = [
        {
            "number": "EXP-000001",
            "contact": "EMPL01",
            "date": "2026-03-15",
            "title": "Client entertainment — ABC Holdings dinner",
            "status": "approved",
            "lines": [
                ("Dinner at Sevva — 4 pax", Decimal("3200.0000"), "6400"),
                ("Taxi to/from Central", Decimal("280.0000"), "6300"),
            ],
        },
        {
            "number": "EXP-000002",
            "contact": "EMPL02",
            "date": "2026-03-20",
            "title": "Professional development — HKICPA seminar",
            "status": "submitted",
            "lines": [
                ("HKICPA Annual Tax Update Seminar registration", Decimal("1500.0000"), "6500"),
                ("MTR and lunch", Decimal("180.0000"), "6300"),
            ],
        },
        {
            "number": "EXP-000003",
            "contact": "EMPL01",
            "date": "2026-04-08",
            "title": "Travel — Shenzhen client visit (DEF Group)",
            "status": "draft",
            "lines": [
                ("Cross-border bus — round trip", Decimal("380.0000"), "6300"),
                ("Lunch with client", Decimal("650.0000"), "6400"),
                ("Local transport (DiDi)", Decimal("220.0000"), "6300"),
            ],
        },
    ]

    for claim_data in claims:
        claim_id = _uid()
        total = sum(line[1] for line in claim_data["lines"])
        claim = ExpenseClaim(
            id=claim_id,
            tenant_id=TENANT_ID,
            number=claim_data["number"],
            contact_id=contacts[claim_data["contact"]],
            status=claim_data["status"],
            claim_date=claim_data["date"],
            title=claim_data["title"],
            currency="HKD",
            total_amount=total,
            tax_total=Decimal("0.0000"),
            approved_by=ACTOR_ID if claim_data["status"] == "approved" else None,
            approved_at=_now() if claim_data["status"] == "approved" else None,
            created_by=ACTOR_ID,
            updated_by=ACTOR_ID,
        )
        db.add(claim)

        for desc, amount, acc_code in claim_data["lines"]:
            line = ExpenseClaimLine(
                id=_uid(),
                tenant_id=TENANT_ID,
                claim_id=claim_id,
                account_id=accs[acc_code],
                description=desc,
                amount=amount,
                tax_amount=Decimal("0.0000"),
                created_by=ACTOR_ID,
                updated_by=ACTOR_ID,
            )
            db.add(line)

    await db.flush()
    print(f"  [ok] {len(claims)} expense claims")


async def seed_fixed_assets(
    db: AsyncSession,
    accs: dict[str, str],
) -> None:
    """Create 3 fixed assets."""
    assets = [
        {
            "name": "Office Furniture — desks, chairs, shelving",
            "category": "furniture",
            "acquisition_date": "2024-06-01",
            "cost": Decimal("120000.0000"),
            "residual": Decimal("12000.0000"),
            "life_months": 60,
            "method": "straight_line",
            "asset_acc": "1500",
            "depr_acc": "6700",
            "accum_acc": "1550",
        },
        {
            "name": "Computer Equipment — workstations and servers",
            "category": "equipment",
            "acquisition_date": "2024-06-01",
            "cost": Decimal("85000.0000"),
            "residual": Decimal("0.0000"),
            "life_months": 60,
            "method": "straight_line",
            "asset_acc": "1510",
            "depr_acc": "6700",
            "accum_acc": "1560",
        },
        {
            "name": "Leasehold Improvements — office fit-out",
            "category": "leasehold_improvement",
            "acquisition_date": "2024-06-01",
            "cost": Decimal("350000.0000"),
            "residual": Decimal("10000.0000"),
            "life_months": 120,
            "method": "straight_line",
            "asset_acc": "1520",
            "depr_acc": "6700",
            "accum_acc": "1570",
        },
    ]

    for asset in assets:
        fa = FixedAsset(
            id=_uid(),
            tenant_id=TENANT_ID,
            name=asset["name"],
            category=asset["category"],
            acquisition_date=asset["acquisition_date"],
            cost=asset["cost"],
            residual_value=asset["residual"],
            useful_life_months=asset["life_months"],
            depreciation_method=asset["method"],
            asset_account_id=accs[asset["asset_acc"]],
            depreciation_account_id=accs[asset["depr_acc"]],
            accumulated_depreciation_account_id=accs[asset["accum_acc"]],
            status="active",
            created_by=ACTOR_ID,
            updated_by=ACTOR_ID,
        )
        db.add(fa)

    await db.flush()
    print(f"  [ok] {len(assets)} fixed assets")


async def seed_projects(
    db: AsyncSession,
    contacts: dict[str, str],
) -> dict[str, str]:
    """Create 4 projects."""
    projects_data = [
        {
            "code": "PRJ-001",
            "name": "ABC Holdings Audit FY2025",
            "contact": "ABCHOLD",
            "status": "active",
            "budget_hours": Decimal("200.00"),
            "budget_amount": Decimal("440000.0000"),
            "currency": "HKD",
        },
        {
            "code": "PRJ-002",
            "name": "XYZ Corp Tax Advisory",
            "contact": "XYZCORP",
            "status": "active",
            "budget_hours": Decimal("150.00"),
            "budget_amount": Decimal("420000.0000"),
            "currency": "HKD",
        },
        {
            "code": "PRJ-003",
            "name": "DEF Group Restructuring",
            "contact": "DEFGRP",
            "status": "active",
            "budget_hours": Decimal("300.00"),
            "budget_amount": Decimal("750000.0000"),
            "currency": "HKD",
        },
        {
            "code": "PRJ-004",
            "name": "GHI Training Program FY2026",
            "contact": "GHIEDU",
            "status": "completed",
            "budget_hours": Decimal("80.00"),
            "budget_amount": Decimal("120000.0000"),
            "currency": "HKD",
        },
    ]

    ids: dict[str, str] = {}
    for p in projects_data:
        proj = Project(
            id=_uid(),
            tenant_id=TENANT_ID,
            contact_id=contacts[p["contact"]],
            name=p["name"],
            code=p["code"],
            status=p["status"],
            budget_hours=p["budget_hours"],
            budget_amount=p["budget_amount"],
            currency=p["currency"],
            created_by=ACTOR_ID,
            updated_by=ACTOR_ID,
        )
        db.add(proj)
        ids[p["code"]] = proj.id

    await db.flush()
    print(f"  [ok] {len(projects_data)} projects")
    return ids


async def seed_time_entries(
    db: AsyncSession,
    project_ids: dict[str, str],
) -> None:
    """Create 50+ time entries across projects."""
    # Generate realistic time entries for each project
    entries = []

    # PRJ-001: ABC Holdings Audit — Nov to Apr, ~120 hours
    prj1_dates = [
        ("2025-11-05", Decimal("6.00"), "Audit planning and risk assessment"),
        ("2025-11-08", Decimal("7.50"), "Walkthrough of revenue recognition process"),
        ("2025-11-12", Decimal("8.00"), "Testing accounts receivable balances"),
        ("2025-11-18", Decimal("6.50"), "Cash and bank confirmations"),
        ("2025-11-22", Decimal("5.00"), "Review of related party transactions"),
        ("2025-12-03", Decimal("8.00"), "Inventory observation and count"),
        ("2025-12-10", Decimal("7.00"), "Testing fixed asset additions and disposals"),
        ("2025-12-15", Decimal("6.00"), "Payroll testing — sample selection"),
        ("2026-01-05", Decimal("8.00"), "Year-end cut-off testing"),
        ("2026-01-12", Decimal("7.50"), "Review management estimates"),
        ("2026-01-20", Decimal("6.00"), "Consolidation adjustments review"),
        ("2026-02-05", Decimal("8.00"), "Draft audit report preparation"),
        ("2026-02-15", Decimal("5.50"), "Management representation letter"),
        ("2026-03-01", Decimal("7.00"), "Partner review and sign-off preparation"),
        ("2026-03-10", Decimal("6.00"), "Final audit report issuance"),
        ("2026-03-20", Decimal("5.00"), "Post-audit debrief with client"),
    ]
    for entry_date, hours, desc in prj1_dates:
        entries.append((project_ids["PRJ-001"], ACTOR_ID, entry_date, hours, desc, True, "approved"))

    # PRJ-002: XYZ Corp Tax Advisory — Dec to Mar, ~90 hours
    prj2_dates = [
        ("2025-12-05", Decimal("6.00"), "Review of current tax structure"),
        ("2025-12-12", Decimal("7.00"), "Transfer pricing documentation review"),
        ("2025-12-18", Decimal("5.50"), "Analysis of cross-border transactions"),
        ("2026-01-08", Decimal("8.00"), "Preparation of profits tax computation"),
        ("2026-01-15", Decimal("7.00"), "Review of tax incentive eligibility"),
        ("2026-01-22", Decimal("6.50"), "Draft tax advisory memorandum"),
        ("2026-02-02", Decimal("8.00"), "Meeting with IRD on objection case"),
        ("2026-02-10", Decimal("5.00"), "Supplemental submission preparation"),
        ("2026-02-20", Decimal("7.50"), "Amended profits tax return preparation"),
        ("2026-03-05", Decimal("6.00"), "Tax provision analysis for Q1 accounts"),
        ("2026-03-15", Decimal("5.50"), "Tax compliance calendar update"),
        ("2026-03-28", Decimal("4.00"), "Client progress review meeting"),
    ]
    for entry_date, hours, desc in prj2_dates:
        entries.append((project_ids["PRJ-002"], ACTOR2_ID, entry_date, hours, desc, True, "approved"))

    # PRJ-003: DEF Group Restructuring — Nov to Apr, ~150 hours
    prj3_dates = [
        ("2025-11-03", Decimal("6.00"), "Initial group structure analysis"),
        ("2025-11-10", Decimal("8.00"), "Review of shareholder agreements"),
        ("2025-11-20", Decimal("7.00"), "Tax implications of proposed restructuring"),
        ("2025-12-01", Decimal("8.00"), "Valuation of inter-company assets"),
        ("2025-12-08", Decimal("6.50"), "Draft restructuring proposal — Option A"),
        ("2025-12-20", Decimal("7.00"), "Draft restructuring proposal — Option B"),
        ("2026-01-10", Decimal("8.00"), "Board presentation preparation"),
        ("2026-01-18", Decimal("5.50"), "Regulatory filing requirements research"),
        ("2026-01-25", Decimal("7.00"), "Stamp duty analysis"),
        ("2026-02-08", Decimal("8.00"), "Implementation timeline and checklist"),
        ("2026-02-18", Decimal("6.00"), "Coordination with legal counsel"),
        ("2026-02-28", Decimal("7.50"), "Draft Companies Ordinance filings"),
        ("2026-03-08", Decimal("8.00"), "Tax clearance application drafting"),
        ("2026-03-18", Decimal("6.00"), "Revised group structure documentation"),
        ("2026-03-30", Decimal("5.00"), "Progress update to board"),
        ("2026-04-05", Decimal("8.00"), "Final implementation support"),
        ("2026-04-12", Decimal("7.00"), "Post-restructuring compliance review"),
    ]
    for entry_date, hours, desc in prj3_dates:
        user = ACTOR_ID if prj3_dates.index((entry_date, hours, desc)) % 2 == 0 else ACTOR2_ID
        entries.append((project_ids["PRJ-003"], user, entry_date, hours, desc, True, "approved"))

    # PRJ-004: GHI Training — Dec to Jan, ~50 hours (completed)
    prj4_dates = [
        ("2025-12-01", Decimal("6.00"), "Training needs assessment"),
        ("2025-12-05", Decimal("8.00"), "Curriculum design — HKFRS update"),
        ("2025-12-10", Decimal("7.00"), "Training materials preparation"),
        ("2025-12-15", Decimal("8.00"), "Corporate governance module development"),
        ("2025-12-20", Decimal("5.00"), "Workshop logistics coordination"),
        ("2026-01-05", Decimal("8.00"), "Delivery — Day 1: Financial Reporting"),
        ("2026-01-06", Decimal("8.00"), "Delivery — Day 2: Corporate Governance"),
    ]
    for entry_date, hours, desc in prj4_dates:
        entries.append((project_ids["PRJ-004"], ACTOR2_ID, entry_date, hours, desc, True, "approved"))

    for project_id, user_id, entry_date, hours, desc, billable, approval in entries:
        te = TimeEntry(
            id=_uid(),
            tenant_id=TENANT_ID,
            project_id=project_id,
            user_id=user_id,
            entry_date=entry_date,
            hours=hours,
            description=desc,
            is_billable=billable,
            approval_status=approval,
            created_by=user_id,
            updated_by=user_id,
        )
        db.add(te)

    await db.flush()
    print(f"  [ok] {len(entries)} time entries across 4 projects")


async def seed_billing_rates(
    db: AsyncSession,
    project_ids: dict[str, str],
) -> None:
    """Create billing rates for projects."""
    rates = [
        # PRJ-001: ABC Holdings Audit
        (project_ids["PRJ-001"], ACTOR_ID, "Partner", Decimal("2800.0000"), "2025-11-01"),
        (project_ids["PRJ-001"], ACTOR2_ID, "Senior Associate", Decimal("1800.0000"), "2025-11-01"),
        # PRJ-002: XYZ Corp Tax
        (project_ids["PRJ-002"], ACTOR_ID, "Partner", Decimal("3000.0000"), "2025-12-01"),
        (project_ids["PRJ-002"], ACTOR2_ID, "Senior Associate", Decimal("2000.0000"), "2025-12-01"),
        # PRJ-003: DEF Group
        (project_ids["PRJ-003"], ACTOR_ID, "Partner", Decimal("2500.0000"), "2025-11-01"),
        (project_ids["PRJ-003"], ACTOR2_ID, "Senior Associate", Decimal("1600.0000"), "2025-11-01"),
        # PRJ-004: GHI Training
        (project_ids["PRJ-004"], ACTOR2_ID, "Trainer", Decimal("2200.0000"), "2025-12-01"),
    ]

    for proj_id, user_id, role, rate, eff_from in rates:
        br = BillingRate(
            id=_uid(),
            tenant_id=TENANT_ID,
            project_id=proj_id,
            user_id=user_id,
            role=role,
            rate=rate,
            currency="HKD",
            effective_from=eff_from,
            created_by=ACTOR_ID,
            updated_by=ACTOR_ID,
        )
        db.add(br)

    await db.flush()
    print(f"  [ok] {len(rates)} billing rates")


async def seed_salary_records(
    db: AsyncSession,
    contacts: dict[str, str],
    periods: dict[str, str],
) -> None:
    """Create monthly salary records with MPF for 2 employees across 6 months."""
    employees = [
        ("EMPL01", Decimal("55000.0000")),  # Kelvin Cheung
        ("EMPL02", Decimal("42000.0000")),  # Sarah Wong
    ]

    period_names = ["2025-11", "2025-12", "2026-01", "2026-02", "2026-03", "2026-04"]
    mpf_cap = Decimal("1500.0000")  # HK MPF cap per month per employer/employee

    count = 0
    for empl_code, gross in employees:
        for period_name in period_names:
            if period_name not in periods:
                continue
            # MPF: 5% of relevant income, capped at HK$1,500
            mpf_contrib = min(gross * Decimal("0.05"), mpf_cap)
            net = gross - mpf_contrib  # employee MPF deducted from gross
            sr = SalaryRecord(
                id=_uid(),
                tenant_id=TENANT_ID,
                employee_contact_id=contacts[empl_code],
                period_id=periods[period_name],
                gross_salary=gross,
                employer_mpf=mpf_contrib,
                employee_mpf=mpf_contrib,
                net_pay=net,
                mpf_scheme_name="HSBC MPF SuperTrust Plus",
                payment_date=f"{period_name[:4]}-{period_name[5:]}-28",
                created_by=ACTOR_ID,
                updated_by=ACTOR_ID,
            )
            db.add(sr)
            count += 1

    await db.flush()
    print(f"  [ok] {count} salary records (2 employees x 6 months)")


async def seed_budget(
    db: AsyncSession,
    accs: dict[str, str],
) -> None:
    """Create FY2026 annual budget with monthly allocations."""
    budget_id = _uid()
    budget = Budget(
        id=budget_id,
        tenant_id=TENANT_ID,
        fiscal_year=2026,
        name="FY2026 Operating Budget",
        status="active",
        created_by=ACTOR_ID,
        updated_by=ACTOR_ID,
    )
    db.add(budget)

    # Monthly budget allocations for key expense accounts
    # (account_code, monthly amounts Jan-Dec in HKD)
    budget_lines_data = [
        ("5000", [Decimal("280000")] * 12),  # Salaries
        ("5100", [Decimal("14000")] * 12),   # MPF
        ("6000", [Decimal("65000")] * 12),   # Rent
        ("6100", [Decimal("3500")] * 12),    # Utilities
        ("6200", [Decimal("3000")] * 12),    # Insurance (amortized)
        ("6300", [Decimal("5000"), Decimal("3000"), Decimal("8000"), Decimal("5000"),
                  Decimal("10000"), Decimal("3000"), Decimal("5000"), Decimal("3000"),
                  Decimal("8000"), Decimal("5000"), Decimal("3000"), Decimal("5000")]),  # Travel
        ("6400", [Decimal("4000"), Decimal("6000"), Decimal("3000"), Decimal("4000"),
                  Decimal("5000"), Decimal("8000"), Decimal("4000"), Decimal("3000"),
                  Decimal("6000"), Decimal("5000"), Decimal("10000"), Decimal("8000")]),  # Entertainment
        ("6500", [Decimal("2000")] * 12),    # Prof development
        ("6600", [Decimal("12000")] * 12),   # Software
        ("6700", [Decimal("6250")] * 12),    # Depreciation
        ("6800", [Decimal("500")] * 12),     # Bank charges
        ("6900", [Decimal("2000")] * 12),    # Printing
        ("7000", [Decimal("1000")] * 12),    # Courier
        ("7200", [Decimal("2000")] * 12),    # Telephone
    ]

    count = 0
    for acc_code, monthly in budget_lines_data:
        bl = BudgetLine(
            id=_uid(),
            tenant_id=TENANT_ID,
            budget_id=budget_id,
            account_id=accs[acc_code],
            month_1=monthly[0],
            month_2=monthly[1],
            month_3=monthly[2],
            month_4=monthly[3],
            month_5=monthly[4],
            month_6=monthly[5],
            month_7=monthly[6],
            month_8=monthly[7],
            month_9=monthly[8],
            month_10=monthly[9],
            month_11=monthly[10],
            month_12=monthly[11],
            created_by=ACTOR_ID,
            updated_by=ACTOR_ID,
        )
        db.add(bl)
        count += 1

    await db.flush()
    print(f"  [ok] 1 budget with {count} line items")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main() -> None:
    print("\n=== Seeding Aegis ERP demo data (Dragon Advisory Ltd) ===\n")

    async with AsyncSessionLocal() as db:
        # Set RLS tenant for the session
        await db.execute(text(f"SET LOCAL app.tenant_id = '{TENANT_ID}'"))

        # Check if already seeded
        count = await db.scalar(
            select(func.count()).select_from(Account).where(Account.tenant_id == TENANT_ID)
        )
        if count and count > 0:
            print(
                f"Already seeded ({count} accounts found for demo tenant). "
                "Run with --force to re-seed."
            )
            if "--force" not in sys.argv:
                return
            print("  Clearing existing seed data...\n")
            # Delete in dependency order (children first)
            for tbl in [
                "time_entries",
                "billing_rates",
                "projects",
                "budget_lines",
                "budgets",
                "salary_records",
                "fixed_assets",
                "bank_transactions",
                "bank_reconciliations",
                "bank_accounts",
                "expense_claim_lines",
                "expense_claims",
                "payment_allocations",
                "payments",
                "bill_lines",
                "bills",
                "invoice_lines",
                "invoices",
                "journal_lines",
                "journal_entries",
                "items",
                "tax_codes",
                "contacts",
                "accounts",
                "periods",
            ]:
                await db.execute(text(f"DELETE FROM {tbl} WHERE tenant_id = '{TENANT_ID}'"))
            # Delete FX rates (no tenant_id)
            await db.execute(text("DELETE FROM fx_rates WHERE source = 'manual'"))
            await db.execute(text(f"DELETE FROM memberships WHERE tenant_id = '{TENANT_ID}'"))
            await db.execute(text(f"DELETE FROM users WHERE id = '{ACTOR_ID}'"))
            await db.execute(text(f"DELETE FROM users WHERE id = '{ACTOR2_ID}'"))
            await db.execute(text(f"DELETE FROM tenants WHERE id = '{TENANT_ID}'"))
            await db.commit()
            # Re-set RLS after commit
            await db.execute(text(f"SET LOCAL app.tenant_id = '{TENANT_ID}'"))

        # 1. Create demo tenant
        db.add(
            Tenant(
                id=TENANT_ID,
                name="Dragon Advisory Ltd",
                legal_name="Dragon Advisory Limited",
                country="HK",
                functional_currency="HKD",
                fiscal_year_start_month=4,  # HK fiscal year: Apr-Mar
                timezone="Asia/Hong_Kong",
                region="apac",
                status="active",
            )
        )
        await db.flush()
        print("  [ok] Demo tenant: Dragon Advisory Ltd (HK)")

        # 2. Create admin users
        user1 = User(
            id=ACTOR_ID,
            email="demo@dragonadvisory.com.hk",
            display_name="Raymond Leung",
            password_hash=hash_password("Demo1234!"),
            locale="en",
        )
        db.add(user1)

        user2 = User(
            id=ACTOR2_ID,
            email="sarah@dragonadvisory.com.hk",
            display_name="Sarah Wong",
            password_hash=hash_password("Demo1234!"),
            locale="en",
        )
        db.add(user2)
        await db.flush()

        m1 = Membership(
            id=_uid(),
            tenant_id=TENANT_ID,
            user_id=ACTOR_ID,
            role="admin",
            status="active",
            joined_at=_now(),
        )
        db.add(m1)

        m2 = Membership(
            id=_uid(),
            tenant_id=TENANT_ID,
            user_id=ACTOR2_ID,
            role="accountant",
            status="active",
            joined_at=_now(),
        )
        db.add(m2)
        await db.flush()
        print("  [ok] Admin user: demo@dragonadvisory.com.hk / Demo1234!")
        print("  [ok] Accountant user: sarah@dragonadvisory.com.hk / Demo1234!")

        # 3. Chart of accounts
        accs = await seed_accounts(db)

        # 4. Periods
        periods = await seed_periods(db)

        # 5. Contacts
        contacts = await seed_contacts(db)

        # 6. Tax codes
        tax_codes = await seed_tax_codes(db, accs)

        # 7. Items / products
        items = await seed_items(db, accs)

        # 8. FX rates
        await seed_fx_rates(db)

        # 9. Journal entries
        je_ids = await seed_journals(db, accs, periods)

        # 10. Invoices
        inv_ids = await seed_invoices(db, accs, contacts, items)

        # 11. Bills
        bill_ids = await seed_bills(db, accs, contacts)

        # 12. Payments
        await seed_payments(db, accs, contacts, inv_ids, bill_ids)

        # 13. Bank accounts
        bank_accounts = await seed_bank_accounts(db, accs)

        # 14. Bank transactions
        await seed_bank_transactions(db, bank_accounts)

        # 15. Expense claims
        await seed_expense_claims(db, accs, contacts)

        # 16. Fixed assets
        await seed_fixed_assets(db, accs)

        # 17. Projects
        project_ids = await seed_projects(db, contacts)

        # 18. Time entries
        await seed_time_entries(db, project_ids)

        # 19. Billing rates
        await seed_billing_rates(db, project_ids)

        # 20. Salary records
        await seed_salary_records(db, contacts, periods)

        # 21. Budget
        await seed_budget(db, accs)

        await db.commit()

    print("\n=== Demo seed complete ===")
    print("  Tenant:     Dragon Advisory Ltd")
    print(f"  Tenant ID:  {TENANT_ID}")
    print("  Admin:      demo@dragonadvisory.com.hk / Demo1234!")
    print("  Accountant: sarah@dragonadvisory.com.hk / Demo1234!")
    print("  Currency:   HKD (functional) + USD/GBP transactions")
    print("  Periods:    Nov 2025 - Apr 2026 (4 closed, 2 open)")
    print()


if __name__ == "__main__":
    asyncio.run(main())
