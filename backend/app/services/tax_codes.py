"""Tax code CRUD service with country preset loader."""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.infra.models import TaxCode

log = get_logger(__name__)


class TaxCodeNotFoundError(ValueError):
    pass


class TaxCodeConflictError(ValueError):
    pass


# ---------------------------------------------------------------------------
# Country presets — seeded on tenant creation
# ---------------------------------------------------------------------------

_PRESETS: dict[str, list[dict]] = {
    "AU": [
        {"code": "GST", "name": "GST on Income", "rate": "0.100000", "tax_type": "output"},
        {"code": "GSTP", "name": "GST on Expenses", "rate": "0.100000", "tax_type": "input"},
        {"code": "GSTFREE", "name": "GST Free Income", "rate": "0.000000", "tax_type": "zero"},
        {"code": "GSTFREEP", "name": "GST Free Expenses", "rate": "0.000000", "tax_type": "zero"},
        {"code": "EXEMPT", "name": "GST Exempt", "rate": "0.000000", "tax_type": "exempt"},
    ],
    "GB": [
        {"code": "VAT20", "name": "VAT Standard 20%", "rate": "0.200000", "tax_type": "output"},
        {"code": "VAT20P", "name": "VAT Input 20%", "rate": "0.200000", "tax_type": "input"},
        {"code": "VAT5", "name": "VAT Reduced 5%", "rate": "0.050000", "tax_type": "output"},
        {"code": "ZERO", "name": "Zero Rated", "rate": "0.000000", "tax_type": "zero"},
        {"code": "EXEMPT", "name": "Exempt", "rate": "0.000000", "tax_type": "exempt"},
    ],
    "SG": [
        {"code": "GST9", "name": "GST 9%", "rate": "0.090000", "tax_type": "output"},
        {"code": "GST9P", "name": "GST Input 9%", "rate": "0.090000", "tax_type": "input"},
        {"code": "ZERO", "name": "Zero-rated", "rate": "0.000000", "tax_type": "zero"},
        {"code": "EXEMPT", "name": "Exempt", "rate": "0.000000", "tax_type": "exempt"},
    ],
    "HK": [
        {"code": "NOTAX", "name": "No Tax (HK)", "rate": "0.000000", "tax_type": "exempt"},
    ],
    "US": [
        # US sales tax varies by state — seeded as stubs only
        {"code": "USSTD", "name": "US Sales Tax (override rate per state)", "rate": "0.000000", "tax_type": "output"},
        {"code": "EXEMPT", "name": "Exempt", "rate": "0.000000", "tax_type": "exempt"},
    ],
}

# Fallback for any country not listed
_DEFAULT_PRESET: list[dict] = [
    {"code": "TAX", "name": "Standard Tax", "rate": "0.000000", "tax_type": "output"},
    {"code": "EXEMPT", "name": "Exempt", "rate": "0.000000", "tax_type": "exempt"},
]


async def seed_country_presets(
    db: AsyncSession, tenant_id: str, country: str, actor_id: str | None = None
) -> list[TaxCode]:
    presets = _PRESETS.get(country.upper(), _DEFAULT_PRESET)
    created: list[TaxCode] = []
    for p in presets:
        # Upsert-style: skip if code already exists for tenant
        existing = await db.scalar(
            select(TaxCode.id).where(
                TaxCode.tenant_id == tenant_id, TaxCode.code == p["code"]
            )
        )
        if existing:
            continue
        tc = TaxCode(
            tenant_id=tenant_id,
            code=p["code"],
            name=p["name"],
            rate=Decimal(p["rate"]),
            tax_type=p["tax_type"],
            country=country.upper(),
            created_by=actor_id,
            updated_by=actor_id,
        )
        db.add(tc)
        created.append(tc)
    if created:
        await db.flush()
    return created


async def create_tax_code(
    db: AsyncSession,
    tenant_id: str,
    actor_id: str | None,
    *,
    code: str,
    name: str,
    rate: Decimal,
    tax_type: str,
    country: str,
    tax_collected_account_id: str | None = None,
    tax_paid_account_id: str | None = None,
) -> TaxCode:
    exists = await db.scalar(
        select(TaxCode.id).where(
            TaxCode.tenant_id == tenant_id, TaxCode.code == code
        )
    )
    if exists:
        raise TaxCodeConflictError(f"Tax code '{code}' already exists")

    tc = TaxCode(
        tenant_id=tenant_id,
        code=code,
        name=name,
        rate=rate,
        tax_type=tax_type,
        country=country.upper(),
        tax_collected_account_id=tax_collected_account_id,
        tax_paid_account_id=tax_paid_account_id,
        created_by=actor_id,
        updated_by=actor_id,
    )
    db.add(tc)
    await db.flush()
    await db.refresh(tc)
    log.info("tax_code.created", tenant_id=tenant_id, code=code)
    return tc


async def list_tax_codes(
    db: AsyncSession,
    tenant_id: str,
    *,
    country: str | None = None,
    active_only: bool = True,
    limit: int = 100,
) -> list[TaxCode]:
    q = select(TaxCode).where(TaxCode.tenant_id == tenant_id)
    if active_only:
        q = q.where(TaxCode.is_active.is_(True))
    if country:
        q = q.where(TaxCode.country == country.upper())
    q = q.order_by(TaxCode.code).limit(limit)
    result = await db.execute(q)
    return list(result.scalars())


async def get_tax_code(db: AsyncSession, tenant_id: str, tax_code_id: str) -> TaxCode:
    tc = await db.scalar(
        select(TaxCode).where(
            TaxCode.id == tax_code_id, TaxCode.tenant_id == tenant_id
        )
    )
    if not tc:
        raise TaxCodeNotFoundError(tax_code_id)
    return tc


async def update_tax_code(
    db: AsyncSession, tenant_id: str, tax_code_id: str, actor_id: str | None, updates: dict
) -> TaxCode:
    tc = await get_tax_code(db, tenant_id, tax_code_id)
    allowed = {"name", "rate", "tax_type", "is_active", "tax_collected_account_id", "tax_paid_account_id"}
    for key, val in updates.items():
        if key in allowed:
            setattr(tc, key, val)
    tc.updated_by = actor_id
    tc.version += 1
    await db.flush()
    await db.refresh(tc)
    return tc
