"""
Demo seed script — populates a dev tenant with realistic data.
Run from backend/:
  python scripts/seed.py
"""

from __future__ import annotations

import asyncio
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

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.infra.models import (
    Account,
    Bill,
    BillLine,
    Contact,
    Invoice,
    InvoiceLine,
    JournalEntry,
    JournalLine,
    Period,
    Tenant,
)

DATABASE_URL = os.environ["DATABASE_URL"]
engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

TENANT_ID = "00000000-0000-0000-0000-000000000001"
ACTOR_ID = "00000000-0000-0000-0000-000000000002"


def _uid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(tz=UTC)


# ---------------------------------------------------------------------------
# Chart of Accounts (AU / US hybrid)
# ---------------------------------------------------------------------------

ACCOUNTS = [
    # Assets
    {
        "code": "1000",
        "name": "Cash & Bank",
        "type": "asset",
        "subtype": "bank",
        "normal_balance": "debit",
    },
    {
        "code": "1010",
        "name": "Business Cheque Account",
        "type": "asset",
        "subtype": "bank",
        "normal_balance": "debit",
        "parent": "1000",
    },
    {
        "code": "1020",
        "name": "Savings Account",
        "type": "asset",
        "subtype": "bank",
        "normal_balance": "debit",
        "parent": "1000",
    },
    {
        "code": "1100",
        "name": "Accounts Receivable",
        "type": "asset",
        "subtype": "receivable",
        "normal_balance": "debit",
    },
    {
        "code": "1200",
        "name": "Inventory",
        "type": "asset",
        "subtype": "inventory",
        "normal_balance": "debit",
    },
    {
        "code": "1500",
        "name": "Prepaid Expenses",
        "type": "asset",
        "subtype": "prepaid",
        "normal_balance": "debit",
    },
    {
        "code": "1900",
        "name": "Fixed Assets",
        "type": "asset",
        "subtype": "fixed_asset",
        "normal_balance": "debit",
    },
    {
        "code": "1910",
        "name": "Computer Equipment",
        "type": "asset",
        "subtype": "fixed_asset",
        "normal_balance": "debit",
        "parent": "1900",
    },
    {
        "code": "1920",
        "name": "Accumulated Depreciation",
        "type": "asset",
        "subtype": "contra_asset",
        "normal_balance": "credit",
        "parent": "1900",
    },
    # Liabilities
    {
        "code": "2000",
        "name": "Accounts Payable",
        "type": "liability",
        "subtype": "payable",
        "normal_balance": "credit",
    },
    {
        "code": "2100",
        "name": "GST Collected",
        "type": "liability",
        "subtype": "tax",
        "normal_balance": "credit",
    },
    {
        "code": "2110",
        "name": "GST Paid (ITC)",
        "type": "asset",
        "subtype": "tax",
        "normal_balance": "debit",
    },
    {
        "code": "2200",
        "name": "PAYG Withholding",
        "type": "liability",
        "subtype": "tax",
        "normal_balance": "credit",
    },
    {
        "code": "2500",
        "name": "Loans Payable",
        "type": "liability",
        "subtype": "loan",
        "normal_balance": "credit",
    },
    {
        "code": "2900",
        "name": "Accrued Liabilities",
        "type": "liability",
        "subtype": "accrued",
        "normal_balance": "credit",
    },
    # Equity
    {
        "code": "3000",
        "name": "Owner's Equity",
        "type": "equity",
        "subtype": "equity",
        "normal_balance": "credit",
    },
    {
        "code": "3100",
        "name": "Retained Earnings",
        "type": "equity",
        "subtype": "retained",
        "normal_balance": "credit",
    },
    {
        "code": "3200",
        "name": "Current Year Earnings",
        "type": "equity",
        "subtype": "earnings",
        "normal_balance": "credit",
    },
    # Revenue
    {
        "code": "4000",
        "name": "Revenue",
        "type": "revenue",
        "subtype": "sales",
        "normal_balance": "credit",
    },
    {
        "code": "4100",
        "name": "Consulting Revenue",
        "type": "revenue",
        "subtype": "sales",
        "normal_balance": "credit",
        "parent": "4000",
    },
    {
        "code": "4200",
        "name": "Product Sales",
        "type": "revenue",
        "subtype": "sales",
        "normal_balance": "credit",
        "parent": "4000",
    },
    {
        "code": "4300",
        "name": "Service Revenue",
        "type": "revenue",
        "subtype": "sales",
        "normal_balance": "credit",
        "parent": "4000",
    },
    {
        "code": "4900",
        "name": "Other Income",
        "type": "revenue",
        "subtype": "other",
        "normal_balance": "credit",
    },
    # Expenses
    {
        "code": "5000",
        "name": "Cost of Goods Sold",
        "type": "expense",
        "subtype": "cogs",
        "normal_balance": "debit",
    },
    {
        "code": "6000",
        "name": "Operating Expenses",
        "type": "expense",
        "subtype": "operating",
        "normal_balance": "debit",
    },
    {
        "code": "6100",
        "name": "Salaries & Wages",
        "type": "expense",
        "subtype": "payroll",
        "normal_balance": "debit",
        "parent": "6000",
    },
    {
        "code": "6200",
        "name": "Rent & Occupancy",
        "type": "expense",
        "subtype": "facilities",
        "normal_balance": "debit",
        "parent": "6000",
    },
    {
        "code": "6300",
        "name": "Software & Subscriptions",
        "type": "expense",
        "subtype": "software",
        "normal_balance": "debit",
        "parent": "6000",
    },
    {
        "code": "6400",
        "name": "Marketing & Advertising",
        "type": "expense",
        "subtype": "marketing",
        "normal_balance": "debit",
        "parent": "6000",
    },
    {
        "code": "6500",
        "name": "Professional Services",
        "type": "expense",
        "subtype": "professional",
        "normal_balance": "debit",
        "parent": "6000",
    },
    {
        "code": "6600",
        "name": "Travel & Entertainment",
        "type": "expense",
        "subtype": "travel",
        "normal_balance": "debit",
        "parent": "6000",
    },
    {
        "code": "6700",
        "name": "Depreciation",
        "type": "expense",
        "subtype": "depreciation",
        "normal_balance": "debit",
        "parent": "6000",
    },
    {
        "code": "6800",
        "name": "Bank Charges",
        "type": "expense",
        "subtype": "bank",
        "normal_balance": "debit",
        "parent": "6000",
    },
    {
        "code": "6900",
        "name": "Other Expenses",
        "type": "expense",
        "subtype": "other",
        "normal_balance": "debit",
        "parent": "6000",
    },
]


async def seed_accounts(db: AsyncSession) -> dict[str, str]:
    """Returns code → id mapping."""
    code_to_id: dict[str, str] = {}
    # First pass — create all without parents
    for a in ACCOUNTS:
        acc = Account(
            id=_uid(),
            tenant_id=TENANT_ID,
            code=a["code"],
            name=a["name"],
            type=a["type"],
            subtype=a["subtype"],
            normal_balance=a["normal_balance"],
            currency="AUD",
            is_active=True,
            is_system=False,
            created_by=ACTOR_ID,
            updated_by=ACTOR_ID,
        )
        db.add(acc)
        code_to_id[a["code"]] = acc.id
    await db.flush()
    # Second pass — wire parent_id
    for a in ACCOUNTS:
        if "parent" in a:
            from sqlalchemy import update as sa_update

            await db.execute(
                sa_update(Account)
                .where(Account.id == code_to_id[a["code"]])
                .values(parent_id=code_to_id[a["parent"]])
            )
    await db.flush()
    print(f"  ✓ {len(ACCOUNTS)} accounts")
    return code_to_id


async def seed_periods(db: AsyncSession) -> dict[str, str]:
    """Create 12 months of periods (2025-05 to 2026-04)."""
    periods: dict[str, str] = {}
    months = [
        ("2025-05", date(2025, 5, 1), date(2025, 5, 31)),
        ("2025-06", date(2025, 6, 1), date(2025, 6, 30)),
        ("2025-07", date(2025, 7, 1), date(2025, 7, 31)),
        ("2025-08", date(2025, 8, 1), date(2025, 8, 31)),
        ("2025-09", date(2025, 9, 1), date(2025, 9, 30)),
        ("2025-10", date(2025, 10, 1), date(2025, 10, 31)),
        ("2025-11", date(2025, 11, 1), date(2025, 11, 30)),
        ("2025-12", date(2025, 12, 1), date(2025, 12, 31)),
        ("2026-01", date(2026, 1, 1), date(2026, 1, 31)),
        ("2026-02", date(2026, 2, 1), date(2026, 2, 28)),
        ("2026-03", date(2026, 3, 1), date(2026, 3, 31)),
        ("2026-04", date(2026, 4, 1), date(2026, 4, 30)),
    ]
    for name, start, end in months:
        p = Period(
            id=_uid(),
            tenant_id=TENANT_ID,
            name=name,
            start_date=datetime(start.year, start.month, start.day, tzinfo=UTC),
            end_date=datetime(end.year, end.month, end.day, 23, 59, 59, tzinfo=UTC),
            status="open" if name >= "2026-01" else "soft_closed",
        )
        db.add(p)
        periods[name] = p.id
    await db.flush()
    print(f"  ✓ {len(months)} periods")
    return periods


async def seed_contacts(db: AsyncSession) -> dict[str, str]:
    data = [
        ("ACME", "Acme Corporation", "customer", "billing@acme.example", "+61 2 9000 0001"),
        ("GLOBEX", "Globex Industries", "customer", "accounts@globex.example", "+61 2 9000 0002"),
        ("INIT", "Initech Ltd", "customer", "ar@initech.example", "+61 2 9000 0003"),
        ("WAYNE", "Wayne Enterprises", "customer", "finance@wayne.example", "+1 212 000 0001"),
        ("AWS", "Amazon Web Services", "supplier", "billing@aws.example", "+1 206 000 0001"),
        ("MSFT", "Microsoft Azure", "supplier", "billing@microsoft.example", "+1 425 000 0001"),
        ("JIRA", "Atlassian Pty Ltd", "supplier", "billing@atlassian.example", "+61 2 9000 0100"),
        ("SLACK", "Slack Technologies", "supplier", "billing@slack.example", "+1 415 000 0001"),
        ("RENT", "CBD Office Trust", "supplier", "lease@cbdtrust.example", "+61 2 9000 0200"),
        (
            "LEGAL",
            "Smith & Partners Law",
            "supplier",
            "accounts@smithlaw.example",
            "+61 2 9000 0300",
        ),
    ]
    ids: dict[str, str] = {}
    for code, name, ctype, email, phone in data:
        c = Contact(
            id=_uid(),
            tenant_id=TENANT_ID,
            contact_type=ctype,
            name=name,
            code=code,
            email=email,
            phone=phone,
            currency="AUD",
            created_by=ACTOR_ID,
            updated_by=ACTOR_ID,
        )
        db.add(c)
        ids[code] = c.id
    await db.flush()
    print(f"  ✓ {len(data)} contacts")
    return ids


def _je(
    tenant_id, number, desc, txn_date, period_id, lines: list[dict]
) -> tuple[JournalEntry, list[JournalLine]]:
    txn_dt = datetime.fromisoformat(txn_date).replace(tzinfo=UTC)
    je = JournalEntry(
        id=_uid(),
        tenant_id=tenant_id,
        number=number,
        status="posted",
        description=desc,
        date=txn_dt,
        period_id=period_id,
        currency="AUD",
        source_type="manual",
        total_debit=sum(Decimal(ln["debit"]) for ln in lines),
        total_credit=sum(Decimal(ln["credit"]) for ln in lines),
        posted_at=_now(),
        posted_by=ACTOR_ID,
        created_by=ACTOR_ID,
        updated_by=ACTOR_ID,
    )
    jls = []
    for i, ln in enumerate(lines, 1):
        jls.append(
            JournalLine(
                id=_uid(),
                tenant_id=tenant_id,
                journal_entry_id=je.id,
                line_no=i,
                account_id=ln["account_id"],
                description=ln.get("desc"),
                debit=Decimal(ln["debit"]),
                credit=Decimal(ln["credit"]),
                currency="AUD",
                fx_rate=Decimal("1"),
                functional_debit=Decimal(ln["debit"]),
                functional_credit=Decimal(ln["credit"]),
            )
        )
    return je, jls


async def seed_journals(db: AsyncSession, accs: dict[str, str], periods: dict[str, str]) -> None:
    entries = [
        # Opening balance — cash injection
        (
            "JE-00001",
            "Initial capital injection",
            "2025-05-01",
            "2025-05",
            [
                {
                    "account_id": accs["1010"],
                    "debit": "250000.00",
                    "credit": "0.00",
                    "desc": "Cheque account",
                },
                {
                    "account_id": accs["3000"],
                    "debit": "0.00",
                    "credit": "250000.00",
                    "desc": "Owner's equity",
                },
            ],
        ),
        # Rent May
        (
            "JE-00002",
            "Office rent — May 2025",
            "2025-05-01",
            "2025-05",
            [
                {"account_id": accs["6200"], "debit": "4500.00", "credit": "0.00"},
                {"account_id": accs["1010"], "debit": "0.00", "credit": "4500.00"},
            ],
        ),
        # AWS bill Jun
        (
            "JE-00003",
            "AWS hosting — Jun 2025",
            "2025-06-30",
            "2025-06",
            [
                {"account_id": accs["6300"], "debit": "1200.00", "credit": "0.00"},
                {"account_id": accs["1010"], "debit": "0.00", "credit": "1200.00"},
            ],
        ),
        # Consulting revenue Jul
        (
            "JE-00004",
            "Consulting revenue — Acme Jul 2025",
            "2025-07-15",
            "2025-07",
            [
                {"account_id": accs["1010"], "debit": "22000.00", "credit": "0.00"},
                {"account_id": accs["4100"], "debit": "0.00", "credit": "22000.00"},
            ],
        ),
        # Salaries Jul
        (
            "JE-00005",
            "Salaries — Jul 2025",
            "2025-07-31",
            "2025-07",
            [
                {"account_id": accs["6100"], "debit": "18000.00", "credit": "0.00"},
                {"account_id": accs["1010"], "debit": "0.00", "credit": "18000.00"},
            ],
        ),
        # Marketing Aug
        (
            "JE-00006",
            "Digital marketing — Aug 2025",
            "2025-08-15",
            "2025-08",
            [
                {"account_id": accs["6400"], "debit": "3500.00", "credit": "0.00"},
                {"account_id": accs["1010"], "debit": "0.00", "credit": "3500.00"},
            ],
        ),
        # Product sales Sep
        (
            "JE-00007",
            "Product sales batch — Sep 2025",
            "2025-09-30",
            "2025-09",
            [
                {"account_id": accs["1010"], "debit": "45000.00", "credit": "0.00"},
                {"account_id": accs["4200"], "debit": "0.00", "credit": "45000.00"},
            ],
        ),
        # Legal Oct
        (
            "JE-00008",
            "Legal retainer — Oct 2025",
            "2025-10-01",
            "2025-10",
            [
                {"account_id": accs["6500"], "debit": "2000.00", "credit": "0.00"},
                {"account_id": accs["1010"], "debit": "0.00", "credit": "2000.00"},
            ],
        ),
        # Computer purchase Nov (asset)
        (
            "JE-00009",
            "MacBook Pro — Nov 2025",
            "2025-11-10",
            "2025-11",
            [
                {"account_id": accs["1910"], "debit": "3499.00", "credit": "0.00"},
                {"account_id": accs["1010"], "debit": "0.00", "credit": "3499.00"},
            ],
        ),
        # Revenue Dec
        (
            "JE-00010",
            "Service revenue — Dec 2025",
            "2025-12-20",
            "2025-12",
            [
                {"account_id": accs["1100"], "debit": "55000.00", "credit": "0.00"},
                {"account_id": accs["4300"], "debit": "0.00", "credit": "55000.00"},
            ],
        ),
        # Cash received Dec
        (
            "JE-00011",
            "Customer payment received — Dec 2025",
            "2025-12-28",
            "2025-12",
            [
                {"account_id": accs["1010"], "debit": "55000.00", "credit": "0.00"},
                {"account_id": accs["1100"], "debit": "0.00", "credit": "55000.00"},
            ],
        ),
        # Jan salaries
        (
            "JE-00012",
            "Salaries — Jan 2026",
            "2026-01-31",
            "2026-01",
            [
                {"account_id": accs["6100"], "debit": "19500.00", "credit": "0.00"},
                {"account_id": accs["1010"], "debit": "0.00", "credit": "19500.00"},
            ],
        ),
        # Feb revenue
        (
            "JE-00013",
            "Consulting revenue — Globex Feb 2026",
            "2026-02-14",
            "2026-02",
            [
                {"account_id": accs["1100"], "debit": "38500.00", "credit": "0.00"},
                {"account_id": accs["4100"], "debit": "0.00", "credit": "38500.00"},
            ],
        ),
        # Mar operating
        (
            "JE-00014",
            "Software subscriptions — Mar 2026",
            "2026-03-31",
            "2026-03",
            [
                {"account_id": accs["6300"], "debit": "2800.00", "credit": "0.00"},
                {"account_id": accs["1010"], "debit": "0.00", "credit": "2800.00"},
            ],
        ),
        # Apr revenue
        (
            "JE-00015",
            "Service revenue — Apr 2026",
            "2026-04-10",
            "2026-04",
            [
                {"account_id": accs["1100"], "debit": "62000.00", "credit": "0.00"},
                {"account_id": accs["4300"], "debit": "0.00", "credit": "62000.00"},
            ],
        ),
    ]

    for number, desc, txn_date, period_name, lines in entries:
        je, jls = _je(TENANT_ID, number, desc, txn_date, periods[period_name], lines)
        db.add(je)
        for jl in jls:
            db.add(jl)

    await db.flush()
    print(f"  ✓ {len(entries)} journal entries")


async def seed_invoices(db: AsyncSession, accs: dict[str, str], contacts: dict[str, str]) -> None:
    data = [
        (
            "INV-00001",
            "ACME",
            "2026-02-01",
            "2026-03-01",
            "2026-02",
            "4100",
            "250000",
            "Consulting — Feb 2026",
            "22000.00",
        ),
        (
            "INV-00002",
            "GLOBEX",
            "2026-02-14",
            "2026-03-14",
            "2026-02",
            "4100",
            "250000",
            "Consulting — Feb 2026",
            "38500.00",
        ),
        (
            "INV-00003",
            "INIT",
            "2026-03-01",
            "2026-03-31",
            "2026-03",
            "4300",
            "250000",
            "Service delivery Q1",
            "15000.00",
        ),
        (
            "INV-00004",
            "WAYNE",
            "2026-03-15",
            "2026-04-15",
            "2026-03",
            "4200",
            "250000",
            "Product licence",
            "9900.00",
        ),
        (
            "INV-00005",
            "ACME",
            "2026-04-01",
            "2026-05-01",
            "2026-04",
            "4300",
            "250000",
            "Service retainer Apr",
            "12000.00",
        ),
        (
            "INV-00006",
            "GLOBEX",
            "2026-04-10",
            "2026-05-10",
            "2026-04",
            "4100",
            "250000",
            "Consulting — Apr 2026",
            "50000.00",
        ),
    ]
    statuses = ["paid", "paid", "authorised", "authorised", "draft", "draft"]

    for (number, contact_code, issue, due, period, rev_code, _fx, desc, amount), inv_status in zip(
        data, statuses, strict=False
    ):
        amt = Decimal(amount)
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
            currency="AUD",
            fx_rate=Decimal("1"),
            subtotal=amt,
            tax_total=Decimal("0"),
            total=amt,
            amount_due=amt if inv_status != "paid" else Decimal("0"),
            functional_total=amt,
            created_by=ACTOR_ID,
            updated_by=ACTOR_ID,
        )
        db.add(inv)
        il = InvoiceLine(
            id=_uid(),
            tenant_id=TENANT_ID,
            invoice_id=inv_id,
            line_no=1,
            account_id=accs[rev_code],
            description=desc,
            quantity=Decimal("1"),
            unit_price=amt,
            discount_pct=Decimal("0"),
            line_amount=amt,
            tax_amount=Decimal("0"),
        )
        db.add(il)

    await db.flush()
    print(f"  ✓ {len(data)} invoices")


async def seed_bills(db: AsyncSession, accs: dict[str, str], contacts: dict[str, str]) -> None:
    data = [
        (
            "BILL-00001",
            "AWS",
            "2026-02-28",
            "2026-03-28",
            "2026-02",
            "6300",
            "AWS hosting Feb",
            "1350.00",
            "approved",
        ),
        (
            "BILL-00002",
            "MSFT",
            "2026-02-28",
            "2026-03-28",
            "2026-02",
            "6300",
            "Azure compute Feb",
            "890.00",
            "approved",
        ),
        (
            "BILL-00003",
            "RENT",
            "2026-03-01",
            "2026-03-07",
            "2026-03",
            "6200",
            "Office rent Mar",
            "4500.00",
            "approved",
        ),
        (
            "BILL-00004",
            "JIRA",
            "2026-03-31",
            "2026-04-14",
            "2026-03",
            "6300",
            "Atlassian suite Mar",
            "420.00",
            "approved",
        ),
        (
            "BILL-00005",
            "SLACK",
            "2026-03-31",
            "2026-04-14",
            "2026-03",
            "6300",
            "Slack Pro Mar",
            "180.00",
            "awaiting_approval",
        ),
        (
            "BILL-00006",
            "RENT",
            "2026-04-01",
            "2026-04-07",
            "2026-04",
            "6200",
            "Office rent Apr",
            "4500.00",
            "draft",
        ),
        (
            "BILL-00007",
            "LEGAL",
            "2026-04-05",
            "2026-05-05",
            "2026-04",
            "6500",
            "Legal retainer Apr",
            "2000.00",
            "draft",
        ),
        (
            "BILL-00008",
            "AWS",
            "2026-04-30",
            "2026-05-30",
            "2026-04",
            "6300",
            "AWS hosting Apr",
            "1420.00",
            "draft",
        ),
    ]

    for number, contact_code, issue, due, period, exp_code, desc, amount, bill_status in data:
        amt = Decimal(amount)
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
            currency="AUD",
            fx_rate=Decimal("1"),
            subtotal=amt,
            tax_total=Decimal("0"),
            total=amt,
            amount_due=amt if bill_status != "paid" else Decimal("0"),
            functional_total=amt,
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
            quantity=Decimal("1"),
            unit_price=amt,
            discount_pct=Decimal("0"),
            line_amount=amt,
            tax_amount=Decimal("0"),
        )
        db.add(bl)

    await db.flush()
    print(f"  ✓ {len(data)} bills")


async def main() -> None:
    print("\n🌱 Seeding Aegis ERP demo data…\n")

    async with AsyncSessionLocal() as db:
        # Check if already seeded
        from sqlalchemy import func, select

        count = await db.scalar(
            select(func.count()).select_from(Account).where(Account.tenant_id == TENANT_ID)
        )
        if count and count > 0:
            print(
                f"⚠️  Already seeded ({count} accounts found for demo tenant). Run with --force to re-seed."
            )
            if "--force" not in sys.argv:
                return
            # Delete existing data
            print("  Clearing existing seed data…")
            await db.execute(text(f"DELETE FROM bill_lines WHERE tenant_id = '{TENANT_ID}'"))
            await db.execute(text(f"DELETE FROM bills WHERE tenant_id = '{TENANT_ID}'"))
            await db.execute(text(f"DELETE FROM invoice_lines WHERE tenant_id = '{TENANT_ID}'"))
            await db.execute(text(f"DELETE FROM invoices WHERE tenant_id = '{TENANT_ID}'"))
            await db.execute(text(f"DELETE FROM journal_lines WHERE tenant_id = '{TENANT_ID}'"))
            await db.execute(text(f"DELETE FROM journal_entries WHERE tenant_id = '{TENANT_ID}'"))
            await db.execute(text(f"DELETE FROM accounts WHERE tenant_id = '{TENANT_ID}'"))
            await db.execute(text(f"DELETE FROM periods WHERE tenant_id = '{TENANT_ID}'"))
            await db.execute(text(f"DELETE FROM contacts WHERE tenant_id = '{TENANT_ID}'"))
            await db.commit()

        # Ensure demo tenant exists
        from sqlalchemy import select as sa_select

        tenant = await db.scalar(sa_select(Tenant).where(Tenant.id == TENANT_ID))
        if not tenant:
            db.add(
                Tenant(
                    id=TENANT_ID,
                    name="Aegis Demo Co",
                    legal_name="Aegis Demo Pty Ltd",
                    country="AU",
                    functional_currency="AUD",
                    fiscal_year_start_month=7,
                    timezone="Australia/Sydney",
                    region="apac",
                    status="active",
                )
            )
            await db.flush()
            print("  ✓ Demo tenant created")

        accs = await seed_accounts(db)
        periods = await seed_periods(db)
        contacts = await seed_contacts(db)
        await seed_journals(db, accs, periods)
        await seed_invoices(db, accs, contacts)
        await seed_bills(db, accs, contacts)

        await db.commit()

    print("\n✅ Done! Tenant ID for dev: " + TENANT_ID)
    print(
        "   Set this in your browser: localStorage.setItem('aegis_tenant_id', '"
        + TENANT_ID
        + "')\n"
    )


if __name__ == "__main__":
    asyncio.run(main())
