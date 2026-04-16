"""
Demo seed script — populates a dev tenant with realistic Acme Corp data.
Run from backend/:
  python scripts/seed_demo.py
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
    Contact,
    Invoice,
    InvoiceLine,
    JournalEntry,
    JournalLine,
    Membership,
    Payment,
    PaymentAllocation,
    Period,
    TaxCode,
    Tenant,
    User,
)

DATABASE_URL = os.environ["DATABASE_URL"]
engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

TENANT_ID = "10000000-0000-0000-0000-000000000001"
ACTOR_ID = "10000000-0000-0000-0000-000000000002"


def _uid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(tz=UTC)


# ---------------------------------------------------------------------------
# Chart of Accounts (US business)
# ---------------------------------------------------------------------------

ACCOUNTS = [
    # Assets
    {"code": "1000", "name": "Cash", "type": "asset", "subtype": "bank", "normal_balance": "debit"},
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
        "name": "Sales Tax Payable",
        "type": "liability",
        "subtype": "tax",
        "normal_balance": "credit",
    },
    {
        "code": "2200",
        "name": "Payroll Liabilities",
        "type": "liability",
        "subtype": "payroll",
        "normal_balance": "credit",
    },
    {
        "code": "2500",
        "name": "Loans Payable",
        "type": "liability",
        "subtype": "loan",
        "normal_balance": "credit",
    },
    # Equity
    {
        "code": "3000",
        "name": "Common Stock",
        "type": "equity",
        "subtype": "equity",
        "normal_balance": "credit",
    },
    {
        "code": "3100",
        "name": "Owner's Equity",
        "type": "equity",
        "subtype": "equity",
        "normal_balance": "credit",
    },
    {
        "code": "3200",
        "name": "Retained Earnings",
        "type": "equity",
        "subtype": "retained",
        "normal_balance": "credit",
    },
    # Revenue
    {
        "code": "4000",
        "name": "Sales Revenue",
        "type": "revenue",
        "subtype": "sales",
        "normal_balance": "credit",
    },
    {
        "code": "4100",
        "name": "Service Revenue",
        "type": "revenue",
        "subtype": "sales",
        "normal_balance": "credit",
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
    },
    {
        "code": "6200",
        "name": "Rent & Occupancy",
        "type": "expense",
        "subtype": "facilities",
        "normal_balance": "debit",
    },
    {
        "code": "6300",
        "name": "Software & Subscriptions",
        "type": "expense",
        "subtype": "software",
        "normal_balance": "debit",
    },
    {
        "code": "6400",
        "name": "Marketing & Advertising",
        "type": "expense",
        "subtype": "marketing",
        "normal_balance": "debit",
    },
    {
        "code": "6500",
        "name": "Professional Services",
        "type": "expense",
        "subtype": "professional",
        "normal_balance": "debit",
    },
    {
        "code": "6600",
        "name": "Travel & Entertainment",
        "type": "expense",
        "subtype": "travel",
        "normal_balance": "debit",
    },
    {
        "code": "6900",
        "name": "Other Expenses",
        "type": "expense",
        "subtype": "other",
        "normal_balance": "debit",
    },
]


async def seed_accounts(db: AsyncSession) -> dict[str, str]:
    """Create all accounts, returns code → id mapping."""
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
            currency="USD",
            is_active=True,
            is_system=False,
            created_by=ACTOR_ID,
            updated_by=ACTOR_ID,
        )
        db.add(acc)
        code_to_id[a["code"]] = acc.id
    await db.flush()
    print(f"  ✓ {len(ACCOUNTS)} accounts")
    return code_to_id


async def seed_periods(db: AsyncSession) -> dict[str, str]:
    """Create current month (open) and last month (soft_closed)."""
    today = date.today()
    current_year = today.year
    current_month = today.month

    # Last month
    if current_month == 1:
        last_month = 12
        last_year = current_year - 1
    else:
        last_month = current_month - 1
        last_year = current_year

    import calendar

    periods_data = [
        (
            f"{last_year}-{last_month:02d}",
            date(last_year, last_month, 1),
            date(last_year, last_month, calendar.monthrange(last_year, last_month)[1]),
            "soft_closed",
        ),
        (
            f"{current_year}-{current_month:02d}",
            date(current_year, current_month, 1),
            date(current_year, current_month, calendar.monthrange(current_year, current_month)[1]),
            "open",
        ),
    ]

    period_ids: dict[str, str] = {}
    for name, start, end, period_status in periods_data:
        p = Period(
            id=_uid(),
            tenant_id=TENANT_ID,
            name=name,
            start_date=datetime(start.year, start.month, start.day, tzinfo=UTC),
            end_date=datetime(end.year, end.month, end.day, 23, 59, 59, tzinfo=UTC),
            status=period_status,
        )
        db.add(p)
        period_ids[name] = p.id
    await db.flush()
    print(f"  ✓ {len(periods_data)} periods ({list(period_ids.keys())})")
    return period_ids


async def seed_contacts(db: AsyncSession) -> dict[str, str]:
    """Create 3 customer and 2 supplier contacts."""
    data = [
        # (code, name, type, email)
        ("TECHSOL", "Tech Solutions Inc", "customer", "billing@techsolutions.example"),
        ("GLOBRET", "Global Retail Co", "customer", "accounts@globalretail.example"),
        ("METROSVC", "Metro Services Ltd", "customer", "finance@metroservices.example"),
        ("OFFPRO", "Office Supplies Pro", "supplier", "invoices@officesuppliespro.example"),
        ("CLOUDHOST", "Cloud Hosting Inc", "supplier", "billing@cloudhosting.example"),
    ]
    ids: dict[str, str] = {}
    for code, name, ctype, email in data:
        c = Contact(
            id=_uid(),
            tenant_id=TENANT_ID,
            contact_type=ctype,
            name=name,
            code=code,
            email=email,
            currency="USD",
            created_by=ACTOR_ID,
            updated_by=ACTOR_ID,
        )
        db.add(c)
        ids[code] = c.id
    await db.flush()
    print(f"  ✓ {len(data)} contacts")
    return ids


async def seed_tax_codes(db: AsyncSession, accs: dict[str, str]) -> dict[str, str]:
    """Create GST 10% and Exempt 0%."""
    tax_data = [
        {
            "code": "GST10",
            "name": "GST 10%",
            "rate": Decimal("0.1"),
            "tax_type": "output",
            "collected_code": "2100",
        },
        {
            "code": "EXEMPT",
            "name": "Exempt 0%",
            "rate": Decimal("0"),
            "tax_type": "exempt",
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
            country="US",
            tax_collected_account_id=accs[td["collected_code"]] if td["collected_code"] else None,
            is_active=True,
            created_by=ACTOR_ID,
            updated_by=ACTOR_ID,
        )
        db.add(tc)
        ids[td["code"]] = tc.id
    await db.flush()
    print(f"  ✓ {len(tax_data)} tax codes")
    return ids


def _make_je(
    tenant_id: str,
    number: str,
    desc: str,
    txn_date: str,
    period_id: str,
    lines: list[dict],
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
        currency="USD",
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
                currency="USD",
                fx_rate=Decimal("1"),
                functional_debit=Decimal(ln["debit"]),
                functional_credit=Decimal(ln["credit"]),
            )
        )
    return je, jls


async def seed_journals(
    db: AsyncSession,
    accs: dict[str, str],
    periods: dict[str, str],
) -> dict[str, str]:
    """Create 5 posted journal entries. Returns number → je_id."""
    today = date.today()
    current_period = f"{today.year}-{today.month:02d}"
    if today.month == 1:
        last_period = f"{today.year - 1}-12"
    else:
        last_period = f"{today.year}-{today.month - 1:02d}"

    cur_year = today.year
    cur_month = today.month
    prev_month = today.month - 1 if today.month > 1 else 12
    prev_year = cur_year if today.month > 1 else cur_year - 1

    entries = [
        (
            "JE-00001",
            "Initial capital injection",
            f"{prev_year}-{prev_month:02d}-01",
            last_period,
            [
                {
                    "account_id": accs["1000"],
                    "debit": "100000.00",
                    "credit": "0.00",
                    "desc": "Cash",
                },
                {
                    "account_id": accs["3100"],
                    "debit": "0.00",
                    "credit": "100000.00",
                    "desc": "Owner's equity",
                },
            ],
        ),
        (
            "JE-00002",
            "Office rent payment",
            f"{prev_year}-{prev_month:02d}-05",
            last_period,
            [
                {"account_id": accs["6200"], "debit": "3500.00", "credit": "0.00"},
                {"account_id": accs["1000"], "debit": "0.00", "credit": "3500.00"},
            ],
        ),
        (
            "JE-00003",
            "Software subscriptions",
            f"{prev_year}-{prev_month:02d}-15",
            last_period,
            [
                {"account_id": accs["6300"], "debit": "850.00", "credit": "0.00"},
                {"account_id": accs["1000"], "debit": "0.00", "credit": "850.00"},
            ],
        ),
        (
            "JE-00004",
            "Consulting revenue received",
            f"{cur_year}-{cur_month:02d}-03",
            current_period,
            [
                {"account_id": accs["1000"], "debit": "15000.00", "credit": "0.00"},
                {"account_id": accs["4100"], "debit": "0.00", "credit": "15000.00"},
            ],
        ),
        (
            "JE-00005",
            "Salaries and wages",
            f"{cur_year}-{cur_month:02d}-10",
            current_period,
            [
                {"account_id": accs["6100"], "debit": "12000.00", "credit": "0.00"},
                {"account_id": accs["1000"], "debit": "0.00", "credit": "12000.00"},
            ],
        ),
    ]

    je_ids: dict[str, str] = {}
    for number, desc, txn_date, period_name, lines in entries:
        if period_name not in periods:
            print(f"  ⚠ Skipping JE {number} — period {period_name} not found")
            continue
        je, jls = _make_je(TENANT_ID, number, desc, txn_date, periods[period_name], lines)
        db.add(je)
        for jl in jls:
            db.add(jl)
        je_ids[number] = je.id

    await db.flush()
    print(f"  ✓ {len(je_ids)} journal entries")
    return je_ids


async def seed_invoices(
    db: AsyncSession,
    accs: dict[str, str],
    contacts: dict[str, str],
) -> dict[str, str]:
    """Create 3 invoices: 1 paid, 1 authorised, 1 draft. Returns number → invoice_id."""
    today = date.today()
    cur_month = f"{today.year}-{today.month:02d}"
    f"{today.year}-{today.month - 1:02d}" if today.month > 1 else f"{today.year - 1}-12"

    data = [
        # (number, contact_code, issue_date, due_date, period, rev_acct, description, amount, inv_status)
        (
            "INV-00001",
            "TECHSOL",
            f"{today.year}-{today.month:02d}-01",
            f"{today.year}-{today.month:02d}-31",
            cur_month,
            "4100",
            "Consulting services Jan",
            "8500.00",
            "paid",
        ),
        (
            "INV-00002",
            "GLOBRET",
            f"{today.year}-{today.month:02d}-05",
            f"{today.year}-{today.month + 1 if today.month < 12 else 1:02d}-05",
            cur_month,
            "4000",
            "Product sales batch",
            "12000.00",
            "authorised",
        ),
        (
            "INV-00003",
            "METROSVC",
            f"{today.year}-{today.month:02d}-10",
            None,
            cur_month,
            "4100",
            "Service retainer",
            "5000.00",
            "draft",
        ),
    ]

    inv_ids: dict[str, str] = {}
    for number, contact_code, issue, due, period, rev_code, desc, amount, inv_status in data:
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
            currency="USD",
            fx_rate=Decimal("1"),
            subtotal=amt,
            tax_total=Decimal("0"),
            total=amt,
            amount_due=Decimal("0") if inv_status == "paid" else amt,
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
        inv_ids[number] = inv_id

    await db.flush()
    print(f"  ✓ {len(data)} invoices")
    return inv_ids


async def seed_bills(
    db: AsyncSession,
    accs: dict[str, str],
    contacts: dict[str, str],
) -> dict[str, str]:
    """Create 2 bills: 1 approved, 1 awaiting_approval. Returns number → bill_id."""
    today = date.today()
    cur_month = f"{today.year}-{today.month:02d}"

    data = [
        # (number, contact_code, issue_date, due_date, period, exp_acct, description, amount, bill_status)
        (
            "BILL-00001",
            "OFFPRO",
            f"{today.year}-{today.month:02d}-02",
            f"{today.year}-{today.month:02d}-20",
            cur_month,
            "6000",
            "Office supplies Q1",
            "420.00",
            "approved",
        ),
        (
            "BILL-00002",
            "CLOUDHOST",
            f"{today.year}-{today.month:02d}-01",
            f"{today.year}-{today.month:02d}-28",
            cur_month,
            "6300",
            "Cloud hosting monthly",
            "980.00",
            "awaiting_approval",
        ),
    ]

    bill_ids: dict[str, str] = {}
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
            currency="USD",
            fx_rate=Decimal("1"),
            subtotal=amt,
            tax_total=Decimal("0"),
            total=amt,
            amount_due=amt,
            functional_total=amt,
            approved_by=ACTOR_ID if bill_status == "approved" else None,
            approved_at=_now() if bill_status == "approved" else None,
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
        bill_ids[number] = bill_id

    await db.flush()
    print(f"  ✓ {len(data)} bills")
    return bill_ids


async def seed_payment(
    db: AsyncSession,
    accs: dict[str, str],
    contacts: dict[str, str],
    inv_ids: dict[str, str],
) -> None:
    """Create 1 payment received, allocated to INV-00001."""
    today = date.today()
    payment_id = _uid()
    amt = Decimal("8500.00")

    payment = Payment(
        id=payment_id,
        tenant_id=TENANT_ID,
        number="PAY-00001",
        payment_type="received",
        status="applied",
        contact_id=contacts["TECHSOL"],
        payment_date=f"{today.year}-{today.month:02d}-05",
        amount=amt,
        currency="USD",
        fx_rate=Decimal("1"),
        functional_amount=amt,
        reference="Bank transfer ref TXN-001",
        created_by=ACTOR_ID,
        updated_by=ACTOR_ID,
    )
    db.add(payment)

    alloc = PaymentAllocation(
        id=_uid(),
        tenant_id=TENANT_ID,
        payment_id=payment_id,
        invoice_id=inv_ids["INV-00001"],
        bill_id=None,
        amount=amt,
        currency="USD",
        created_by=ACTOR_ID,
    )
    db.add(alloc)
    await db.flush()
    print("  ✓ 1 payment + 1 allocation")


async def seed_bank_account(
    db: AsyncSession,
    accs: dict[str, str],
) -> str:
    """Create 1 bank account linked to Cash CoA account. Returns bank_account_id."""
    ba = BankAccount(
        id=_uid(),
        tenant_id=TENANT_ID,
        name="Acme Corp Main Checking",
        bank_name="First National Bank",
        account_number="****4321",
        currency="USD",
        coa_account_id=accs["1000"],
        is_active=True,
        created_by=ACTOR_ID,
        updated_by=ACTOR_ID,
    )
    db.add(ba)
    await db.flush()
    print("  ✓ 1 bank account")
    return ba.id


async def seed_bank_transactions(
    db: AsyncSession,
    bank_account_id: str,
) -> None:
    """Create 5 bank transactions (mix of matched and unmatched)."""
    today = date.today()
    cur_month = today.month
    cur_year = today.year

    transactions = [
        {
            "description": "Customer payment — Tech Solutions Inc",
            "amount": Decimal("8500.00"),
            "is_reconciled": True,
        },
        {
            "description": "Office rent payment",
            "amount": Decimal("-3500.00"),
            "is_reconciled": True,
        },
        {
            "description": "Software subscriptions",
            "amount": Decimal("-850.00"),
            "is_reconciled": True,
        },
        {
            "description": "Incoming transfer — pending match",
            "amount": Decimal("2200.00"),
            "is_reconciled": False,
        },
        {
            "description": "Card purchase — office supplies",
            "amount": Decimal("-145.50"),
            "is_reconciled": False,
        },
    ]

    for i, td in enumerate(transactions, 1):
        txn = BankTransaction(
            id=_uid(),
            tenant_id=TENANT_ID,
            bank_account_id=bank_account_id,
            transaction_date=date(cur_year, cur_month, i),
            description=td["description"],
            amount=td["amount"],
            currency="USD",
            is_reconciled=td["is_reconciled"],
            reconciled_at=_now() if td["is_reconciled"] else None,
            created_by=ACTOR_ID,
            updated_by=ACTOR_ID,
        )
        db.add(txn)

    await db.flush()
    print(f"  ✓ {len(transactions)} bank transactions")


async def main() -> None:
    print("\n Seeding Aegis ERP demo data (Acme Corp)…\n")

    async with AsyncSessionLocal() as db:
        # Set RLS tenant for the session
        await db.execute(text(f"SET LOCAL app.tenant_id = '{TENANT_ID}'"))

        # Check if already seeded
        count = await db.scalar(
            select(func.count()).select_from(Account).where(Account.tenant_id == TENANT_ID)
        )
        if count and count > 0:
            print(
                f"Already seeded ({count} accounts found for demo tenant). Run with --force to re-seed."
            )
            if "--force" not in sys.argv:
                return
            print("  Clearing existing seed data…")
            for tbl in [
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
                "tax_codes",
                "contacts",
                "accounts",
                "periods",
            ]:
                await db.execute(text(f"DELETE FROM {tbl} WHERE tenant_id = '{TENANT_ID}'"))
            await db.execute(text(f"DELETE FROM memberships WHERE tenant_id = '{TENANT_ID}'"))
            await db.execute(text(f"DELETE FROM users WHERE id = '{ACTOR_ID}'"))
            await db.execute(text(f"DELETE FROM tenants WHERE id = '{TENANT_ID}'"))
            await db.commit()
            # Re-set RLS after commit
            await db.execute(text(f"SET LOCAL app.tenant_id = '{TENANT_ID}'"))

        # 1. Create demo tenant
        db.add(
            Tenant(
                id=TENANT_ID,
                name="Acme Corp Demo",
                legal_name="Acme Corporation Inc.",
                country="US",
                functional_currency="USD",
                fiscal_year_start_month=1,
                timezone="America/New_York",
                region="us",
                status="active",
            )
        )
        await db.flush()
        print("  ✓ Demo tenant: Acme Corp Demo")

        # 2. Create admin user
        user = User(
            id=ACTOR_ID,
            email="demo@acme.com",
            display_name="Alex Admin",
            password_hash=hash_password("Demo1234!"),
            locale="en",
        )
        db.add(user)
        await db.flush()

        membership = Membership(
            id=_uid(),
            tenant_id=TENANT_ID,
            user_id=ACTOR_ID,
            role="admin",
            status="active",
            joined_at=_now(),
        )
        db.add(membership)
        await db.flush()
        print("  ✓ Admin user: demo@acme.com / Demo1234!")

        # 3. Chart of accounts
        accs = await seed_accounts(db)

        # 4. Periods
        periods = await seed_periods(db)

        # 5. Contacts
        contacts = await seed_contacts(db)

        # 6. Tax codes
        await seed_tax_codes(db, accs)

        # 7. Journal entries
        await seed_journals(db, accs, periods)

        # 8. Invoices
        inv_ids = await seed_invoices(db, accs, contacts)

        # 9. Bills
        await seed_bills(db, accs, contacts)

        # 10. Payment
        await seed_payment(db, accs, contacts, inv_ids)

        # 11. Bank account
        bank_account_id = await seed_bank_account(db, accs)

        # 12. Bank transactions
        await seed_bank_transactions(db, bank_account_id)

        await db.commit()

    print("\n✓ Demo seed complete. Login: demo@acme.com / Demo1234!")
    print(f"  Tenant ID: {TENANT_ID}\n")


if __name__ == "__main__":
    asyncio.run(main())
