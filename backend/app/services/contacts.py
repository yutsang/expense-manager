"""Contact CRUD service (customers, suppliers, employees)."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.infra.models import Contact

log = get_logger(__name__)


class ContactNotFoundError(ValueError):
    pass


class ContactCodeConflictError(ValueError):
    pass


class ComplianceRestrictionError(ValueError):
    """Raised when a compliance policy blocks an operation."""

    pass


class DuplicateContactError(ValueError):
    pass


class EddNotRequiredError(ValueError):
    """Raised when EDD approval is attempted on a contact that does not require it."""

    pass


async def create_contact(
    db: AsyncSession,
    tenant_id: str,
    actor_id: str | None,
    *,
    contact_type: str,
    name: str,
    code: str | None = None,
    email: str | None = None,
    phone: str | None = None,
    currency: str = "USD",
    tax_number: str | None = None,
    address_line1: str | None = None,
    address_line2: str | None = None,
    city: str | None = None,
    region: str | None = None,
    postal_code: str | None = None,
    country: str | None = None,
    credit_limit: str | None = None,
) -> Contact:
    if code:
        exists = await db.scalar(
            select(Contact.id).where(
                Contact.tenant_id == tenant_id,
                Contact.code == code,
                Contact.is_archived.is_(False),
            )
        )
        if exists:
            raise ContactCodeConflictError(f"Contact code '{code}' already in use")

    # ── Duplicate detection by name + tax_number (Issue #14) ───────────────
    if tax_number is not None:
        dup = await db.scalar(
            select(Contact).where(
                Contact.tenant_id == tenant_id,
                func.lower(Contact.name) == name.lower(),
                Contact.tax_number == tax_number,
                Contact.is_archived.is_(False),
            )
        )
        if dup is not None:
            raise DuplicateContactError(
                f"A contact with the same name and tax number already exists: {dup.id}"
            )

    from decimal import Decimal

    contact = Contact(
        tenant_id=tenant_id,
        contact_type=contact_type,
        name=name,
        code=code,
        email=email,
        phone=phone,
        currency=currency,
        tax_number=tax_number,
        address_line1=address_line1,
        address_line2=address_line2,
        city=city,
        region=region,
        postal_code=postal_code,
        country=country,
        credit_limit=Decimal(credit_limit) if credit_limit is not None else None,
        created_by=actor_id,
        updated_by=actor_id,
    )
    db.add(contact)
    await db.flush()
    await db.refresh(contact)
    log.info("contact.created", tenant_id=tenant_id, contact_id=contact.id)
    return contact


async def list_contacts(
    db: AsyncSession,
    tenant_id: str,
    *,
    contact_type: str | None = None,
    include_archived: bool = False,
    limit: int = 50,
    cursor: str | None = None,
) -> list[Contact]:
    q = select(Contact).where(Contact.tenant_id == tenant_id)
    if contact_type:
        q = q.where(Contact.contact_type == contact_type)
    if not include_archived:
        q = q.where(Contact.is_archived.is_(False))
    if cursor:
        q = q.where(Contact.id > cursor)
    q = q.order_by(Contact.name, Contact.id).limit(limit)
    result = await db.execute(q)
    return list(result.scalars())


async def get_contact(db: AsyncSession, tenant_id: str, contact_id: str) -> Contact:
    contact = await db.scalar(
        select(Contact).where(
            Contact.id == contact_id,
            Contact.tenant_id == tenant_id,
        )
    )
    if not contact:
        raise ContactNotFoundError(contact_id)
    return contact


async def update_contact(
    db: AsyncSession,
    tenant_id: str,
    contact_id: str,
    actor_id: str | None,
    updates: dict,
) -> Contact:
    contact = await get_contact(db, tenant_id, contact_id)
    allowed = {
        "name",
        "code",
        "email",
        "phone",
        "currency",
        "tax_number",
        "address_line1",
        "address_line2",
        "city",
        "region",
        "postal_code",
        "country",
        "contact_type",
        "credit_limit",
    }
    for key, val in updates.items():
        if key in allowed:
            setattr(contact, key, val)
    contact.updated_by = actor_id
    contact.version += 1
    await db.flush()
    await db.refresh(contact)
    return contact


async def archive_contact(
    db: AsyncSession, tenant_id: str, contact_id: str, actor_id: str | None
) -> Contact:
    contact = await get_contact(db, tenant_id, contact_id)
    contact.is_archived = True
    contact.updated_by = actor_id
    contact.version += 1
    await db.flush()
    return contact


async def set_risk_rating(
    db: AsyncSession,
    tenant_id: str,
    contact_id: str,
    actor_id: str | None,
    *,
    risk_rating: str,
    risk_rating_rationale: str,
) -> Contact:
    """Set AMLO Cap 615 risk rating for a contact.

    High and unacceptable ratings automatically set edd_required=True.
    Low and medium ratings set edd_required=False and clear EDD approval.
    """
    contact = await get_contact(db, tenant_id, contact_id)
    contact.risk_rating = risk_rating
    contact.risk_rating_rationale = risk_rating_rationale
    contact.risk_rated_by = actor_id
    contact.risk_rated_at = datetime.now(tz=UTC)

    if risk_rating in ("high", "unacceptable"):
        contact.edd_required = True
    else:
        contact.edd_required = False
        contact.edd_approved_by = None
        contact.edd_approved_at = None

    contact.updated_by = actor_id
    contact.version += 1
    await db.flush()
    await db.refresh(contact)
    log.info(
        "contact.risk_rating_set",
        tenant_id=tenant_id,
        contact_id=contact_id,
        risk_rating=risk_rating,
    )
    return contact


async def approve_edd(
    db: AsyncSession,
    tenant_id: str,
    contact_id: str,
    actor_id: str | None,
) -> Contact:
    """Approve Enhanced Due Diligence for a contact.

    Only valid when edd_required=True. Records the approving senior user
    and timestamp.
    """
    contact = await get_contact(db, tenant_id, contact_id)
    if not contact.edd_required:
        raise EddNotRequiredError(
            f"Contact {contact_id} does not require Enhanced Due Diligence approval"
        )
    contact.edd_approved_by = actor_id
    contact.edd_approved_at = datetime.now(tz=UTC)
    contact.updated_by = actor_id
    contact.version += 1
    await db.flush()
    await db.refresh(contact)
    log.info(
        "contact.edd_approved",
        tenant_id=tenant_id,
        contact_id=contact_id,
    )
    return contact
