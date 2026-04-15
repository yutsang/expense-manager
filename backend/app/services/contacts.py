"""Contact CRUD service (customers, suppliers, employees)."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.infra.models import Contact

log = get_logger(__name__)


class ContactNotFoundError(ValueError):
    pass


class ContactCodeConflictError(ValueError):
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
        "name", "code", "email", "phone", "currency", "tax_number",
        "address_line1", "address_line2", "city", "region", "postal_code", "country",
        "contact_type",
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
