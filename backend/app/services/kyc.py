"""KYC / Sanctions service — get_or_create, update, list, dashboard alerts."""
from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.infra.models import Contact, ContactKyc

log = get_logger(__name__)

_STALE_POA_DAYS = 3 * 365  # 3 years in days
_EXPIRY_SOON_DAYS = 60


class KycNotFoundError(ValueError):
    pass


async def get_or_create_kyc(
    db: AsyncSession,
    *,
    contact_id: str,
    tenant_id: str,
) -> ContactKyc:
    """Return existing KYC record or create a blank one."""
    existing = await db.scalar(
        select(ContactKyc).where(
            ContactKyc.contact_id == contact_id,
            ContactKyc.tenant_id == tenant_id,
        )
    )
    if existing:
        return existing

    kyc = ContactKyc(
        tenant_id=tenant_id,
        contact_id=contact_id,
    )
    db.add(kyc)
    await db.flush()
    await db.refresh(kyc)
    log.info("kyc.created", tenant_id=tenant_id, contact_id=contact_id)
    return kyc


async def update_kyc(
    db: AsyncSession,
    *,
    contact_id: str,
    tenant_id: str,
    **fields: Any,
) -> ContactKyc:
    """Update KYC fields and bump version."""
    kyc = await get_or_create_kyc(db, contact_id=contact_id, tenant_id=tenant_id)
    allowed = {
        "id_type", "id_number", "id_expiry_date", "poa_type", "poa_date",
        "sanctions_status", "sanctions_checked_at", "kyc_status",
        "kyc_approved_at", "kyc_approved_by", "last_review_date",
        "next_review_date", "notes", "updated_by",
    }
    for key, val in fields.items():
        if key in allowed:
            setattr(kyc, key, val)
    kyc.version += 1
    kyc.updated_at = datetime.now(tz=UTC)
    await db.flush()
    await db.refresh(kyc)
    log.info("kyc.updated", tenant_id=tenant_id, contact_id=contact_id)
    return kyc


async def list_kyc_summary(
    db: AsyncSession,
    *,
    tenant_id: str,
) -> list[dict]:
    """Return all contacts with their KYC record (left join)."""
    q = (
        select(Contact, ContactKyc)
        .outerjoin(ContactKyc, (ContactKyc.contact_id == Contact.id) & (ContactKyc.tenant_id == tenant_id))
        .where(Contact.tenant_id == tenant_id, Contact.is_archived.is_(False))
        .order_by(Contact.name)
    )
    result = await db.execute(q)
    rows = result.all()

    out: list[dict] = []
    for contact, kyc in rows:
        row: dict = {
            "contact_id": contact.id,
            "contact_name": contact.name,
            "contact_type": contact.contact_type,
            "kyc_id": kyc.id if kyc else None,
            "id_type": kyc.id_type if kyc else None,
            "id_number": kyc.id_number if kyc else None,
            "id_expiry_date": kyc.id_expiry_date if kyc else None,
            "poa_type": kyc.poa_type if kyc else None,
            "poa_date": kyc.poa_date if kyc else None,
            "sanctions_status": kyc.sanctions_status if kyc else "not_checked",
            "sanctions_checked_at": kyc.sanctions_checked_at if kyc else None,
            "kyc_status": kyc.kyc_status if kyc else "pending",
            "kyc_approved_at": kyc.kyc_approved_at if kyc else None,
            "kyc_approved_by": kyc.kyc_approved_by if kyc else None,
            "last_review_date": kyc.last_review_date if kyc else None,
            "next_review_date": kyc.next_review_date if kyc else None,
            "notes": kyc.notes if kyc else None,
            "created_at": kyc.created_at if kyc else None,
            "updated_at": kyc.updated_at if kyc else None,
            "version": kyc.version if kyc else None,
        }
        out.append(row)
    return out


async def get_dashboard_alerts(
    db: AsyncSession,
    *,
    tenant_id: str,
) -> dict[str, int]:
    """Return alert counts for the KYC compliance widget."""
    today = date.today()
    expiry_cutoff = date(today.year, today.month, today.day)
    expiry_soon_cutoff = date.fromordinal(today.toordinal() + _EXPIRY_SOON_DAYS)
    poa_stale_cutoff = date.fromordinal(today.toordinal() - _STALE_POA_DAYS)

    kyc_rows_result = await db.execute(
        select(ContactKyc).where(ContactKyc.tenant_id == tenant_id)
    )
    kyc_rows = list(kyc_rows_result.scalars())

    id_expired = 0
    id_expiring_soon = 0
    poa_stale = 0
    pending_kyc = 0
    flagged = 0

    for kyc in kyc_rows:
        # ID expiry
        if kyc.id_expiry_date is not None:
            expiry = kyc.id_expiry_date if isinstance(kyc.id_expiry_date, date) else kyc.id_expiry_date
            if expiry < expiry_cutoff:
                id_expired += 1
            elif expiry <= expiry_soon_cutoff:
                id_expiring_soon += 1

        # POA stale: poa_date <= today - 3 years, OR poa_date is null and status=approved
        if kyc.poa_date is not None:
            poa = kyc.poa_date if isinstance(kyc.poa_date, date) else kyc.poa_date
            if poa <= poa_stale_cutoff:
                poa_stale += 1
        elif kyc.kyc_status == "approved":
            poa_stale += 1

        # Pending
        if kyc.kyc_status == "pending":
            pending_kyc += 1

        # Flagged
        if kyc.sanctions_status == "flagged" or kyc.kyc_status == "flagged":
            flagged += 1

    return {
        "id_expiring_soon": id_expiring_soon,
        "id_expired": id_expired,
        "poa_stale": poa_stale,
        "pending_kyc": pending_kyc,
        "flagged": flagged,
    }
