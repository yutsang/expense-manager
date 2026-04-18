"""Onboarding service — first-time tenant setup wizard (Issue #34).

Provisions CoA from a template, generates periods, creates first bank account,
and optionally the first contact. Sets setup_completed_at on the tenant.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.infra.models import BankAccount, Contact, Tenant
from app.infra.templates import get_coa_template
from app.services.accounts import create_account
from app.services.periods import provision_periods

log = get_logger(__name__)


class OnboardingAlreadyCompleteError(ValueError):
    pass


class TenantNotFoundError(ValueError):
    pass


# ── CoA template mapping ────────────────────────────────────────────────────
# Maps wizard template names to country codes used by get_coa_template.
# "general" uses the US template; professional_services and retail also use US
# as a base (the templates contain the same structure with industry-appropriate
# accounts).

_TEMPLATE_COUNTRY_MAP: dict[str, str] = {
    "general": "US",
    "professional_services": "US",
    "retail": "US",
}


async def setup_tenant(
    db: AsyncSession,
    *,
    tenant_id: str,
    actor_id: str | None,
    company_name: str,
    legal_name: str,
    country: str,
    functional_currency: str,
    fiscal_year_start_month: int,
    coa_template: str,
    bank_account_name: str,
    bank_name: str | None = None,
    bank_account_number: str | None = None,
    bank_currency: str = "USD",
    first_contact_name: str | None = None,
    first_contact_email: str | None = None,
    first_contact_type: str | None = None,
) -> dict:
    """Run the full onboarding wizard in a single transaction.

    Returns a summary dict with counts of created entities.
    Raises OnboardingAlreadyCompleteError if setup_completed_at is already set.
    """
    # Fetch and validate tenant
    tenant = await db.scalar(select(Tenant).where(Tenant.id == tenant_id))
    if not tenant:
        raise TenantNotFoundError(f"Tenant not found: {tenant_id}")

    if tenant.setup_completed_at is not None:
        raise OnboardingAlreadyCompleteError(f"Tenant {tenant_id} has already completed onboarding")

    # Update tenant details
    tenant.name = company_name
    tenant.legal_name = legal_name
    tenant.country = country
    tenant.functional_currency = functional_currency
    tenant.fiscal_year_start_month = fiscal_year_start_month

    # ── Provision Chart of Accounts ──────────────────────────────────────
    template_country = _TEMPLATE_COUNTRY_MAP.get(coa_template, "US")
    coa_accounts = get_coa_template(template_country)
    accounts_created = 0

    # Build a code->id map for parent resolution
    code_to_id: dict[str, str] = {}
    for acct_def in coa_accounts:
        parent_id = (
            code_to_id.get(acct_def.get("parent_code")) if "parent_code" in acct_def else None
        )
        try:
            acct = await create_account(
                db,
                tenant_id=tenant_id,
                code=acct_def["code"],
                name=acct_def["name"],
                type=acct_def["type"],
                subtype=acct_def.get("subtype", "other"),
                normal_balance=acct_def["normal_balance"],
                parent_id=parent_id,
                is_system=acct_def.get("is_system", False),
                currency=functional_currency,
                actor_id=actor_id,
            )
            code_to_id[acct_def["code"]] = acct.id
            accounts_created += 1
        except ValueError:
            # Account code already exists (idempotent)
            pass

    # ── Provision Periods ──────────────���─────────────────────────────────
    periods = await provision_periods(
        db,
        tenant_id=tenant_id,
        functional_currency=functional_currency,
        fiscal_year_start_month=fiscal_year_start_month,
    )
    periods_created = len(periods)

    # ── Create Bank Account ──────────────────────────────────────────────
    bank_account = BankAccount(
        id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        name=bank_account_name,
        bank_name=bank_name,
        account_number=bank_account_number,
        currency=bank_currency,
        is_active=True,
        created_by=actor_id,
        updated_by=actor_id,
    )
    db.add(bank_account)
    await db.flush()

    # ── Optionally Create First Contact ────────────���─────────────────────
    first_contact_id = None
    if first_contact_name:
        contact = Contact(
            id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            contact_type=first_contact_type or "customer",
            name=first_contact_name,
            email=first_contact_email,
            currency=functional_currency,
            created_by=actor_id,
            updated_by=actor_id,
        )
        db.add(contact)
        await db.flush()
        first_contact_id = contact.id

    # ── Mark setup complete ──────────────────────────────────────────────
    now = datetime.now(tz=UTC)
    tenant.setup_completed_at = now
    tenant.updated_at = now
    tenant.version += 1
    await db.flush()

    log.info(
        "onboarding.completed",
        tenant_id=tenant_id,
        accounts_created=accounts_created,
        periods_created=periods_created,
    )

    return {
        "tenant_id": tenant_id,
        "setup_completed_at": now.isoformat(),
        "accounts_created": accounts_created,
        "periods_created": periods_created,
        "bank_account_id": bank_account.id,
        "first_contact_id": first_contact_id,
    }
