"""Onboarding API — first-time tenant setup wizard (Issue #34)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.api.v1.deps import ActorId, DbSession, TenantId
from app.api.v1.schemas import OnboardingResponse, OnboardingSetup
from app.services.onboarding import (
    OnboardingAlreadyCompleteError,
    TenantNotFoundError,
    setup_tenant,
)

router = APIRouter(prefix="/onboarding", tags=["onboarding"])


@router.post("/setup", response_model=OnboardingResponse, status_code=status.HTTP_201_CREATED)
async def setup(body: OnboardingSetup, db: DbSession, tenant_id: TenantId, actor_id: ActorId):
    """Run the onboarding wizard: provisions CoA, periods, bank account, optional contact."""
    try:
        result = await setup_tenant(
            db,
            tenant_id=tenant_id,
            actor_id=actor_id,
            company_name=body.company_name,
            legal_name=body.legal_name,
            country=body.country,
            functional_currency=body.functional_currency,
            fiscal_year_start_month=body.fiscal_year_start_month,
            coa_template=body.coa_template,
            bank_account_name=body.bank_account_name,
            bank_name=body.bank_name,
            bank_account_number=body.bank_account_number,
            bank_currency=body.bank_currency,
            first_contact_name=body.first_contact_name,
            first_contact_email=body.first_contact_email,
            first_contact_type=body.first_contact_type,
        )
        await db.commit()
        return OnboardingResponse(**result)
    except TenantNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    except OnboardingAlreadyCompleteError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Onboarding already completed for this tenant",
        )
