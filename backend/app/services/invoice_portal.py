"""Invoice portal service — shareable invoice links (Issue #36).

Provides token-based public access to invoices for customers.
Tokens are opaque secrets (URL-safe random bytes), not JWTs, to keep
the implementation simple and stateless from the customer's perspective.
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.infra.models import Contact, Invoice, Tenant
from app.services.invoices import get_invoice

log = get_logger(__name__)

# Statuses from which an invoice can be shared
_SHAREABLE_STATUSES = {"authorised", "sent", "partial", "paid"}


class InvoiceNotShareableError(ValueError):
    pass


class ShareTokenInvalidError(ValueError):
    pass


async def generate_share_link(
    db: AsyncSession,
    *,
    tenant_id: str,
    invoice_id: str,
) -> dict:
    """Generate a share token for the invoice and return the public URL.

    Only authorised/sent/partial/paid invoices can be shared.
    If a token already exists, it is replaced with a new one.
    """
    inv = await get_invoice(db, tenant_id, invoice_id)

    if inv.status not in _SHAREABLE_STATUSES:
        raise InvoiceNotShareableError(
            f"Cannot share invoice in '{inv.status}' status — must be authorised first"
        )

    # Generate a cryptographically secure token
    token = secrets.token_urlsafe(32)
    inv.share_token = token
    inv.updated_at = datetime.now(tz=UTC)
    inv.version += 1

    await db.flush()

    log.info("invoice.share_link_generated", tenant_id=tenant_id, invoice_id=invoice_id)

    return {
        "share_token": token,
        "public_url": f"/pay/{token}",
        "expires_at": "",  # tokens don't expire in v1
    }


async def get_public_invoice(
    db: AsyncSession,
    *,
    share_token: str,
) -> Invoice:
    """Retrieve an invoice by its share token. Sets viewed_at on first access.

    This is called from the unauthenticated public route.
    Raises ShareTokenInvalidError if no invoice matches the token.
    """
    inv = await db.scalar(
        select(Invoice).where(Invoice.share_token == share_token)
    )
    if not inv:
        raise ShareTokenInvalidError("Invalid or expired share link")

    # Record first view
    if inv.viewed_at is None:
        inv.viewed_at = datetime.now(tz=UTC)
        inv.updated_at = datetime.now(tz=UTC)
        await db.flush()

    return inv


async def get_public_invoice_detail(
    db: AsyncSession,
    *,
    share_token: str,
) -> dict:
    """Build the full public-facing invoice detail for the portal page.

    Returns a dict suitable for PublicInvoiceResponse.
    """
    inv = await get_public_invoice(db, share_token=share_token)

    # Fetch the tenant name for the invoice header
    tenant = await db.scalar(select(Tenant).where(Tenant.id == inv.tenant_id))
    company_name = tenant.name if tenant else "Unknown"

    # Fetch contact name
    contact = await db.scalar(select(Contact).where(Contact.id == inv.contact_id))
    contact_name = contact.name if contact else "Unknown"

    # Fetch invoice lines
    from app.services.invoices import get_invoice_lines

    lines = await get_invoice_lines(db, inv.id)

    return {
        "invoice_number": inv.number,
        "status": inv.status,
        "contact_name": contact_name,
        "issue_date": inv.issue_date,
        "due_date": inv.due_date,
        "currency": inv.currency,
        "subtotal": str(inv.subtotal),
        "tax_total": str(inv.tax_total),
        "total": str(inv.total),
        "notes": inv.notes,
        "lines": [
            {
                "description": line.description,
                "quantity": str(line.quantity),
                "unit_price": str(line.unit_price),
                "line_amount": str(line.line_amount),
                "tax_amount": str(line.tax_amount),
            }
            for line in lines
        ],
        "company_name": company_name,
        "acknowledged_at": inv.acknowledged_at.isoformat() if inv.acknowledged_at else None,
    }


async def acknowledge_invoice(
    db: AsyncSession,
    *,
    share_token: str,
    customer_name: str | None = None,
    ip_address: str | None = None,
) -> Invoice:
    """Record customer acknowledgement of an invoice.

    Idempotent: if already acknowledged, returns the existing record unchanged.
    """
    inv = await db.scalar(
        select(Invoice).where(Invoice.share_token == share_token)
    )
    if not inv:
        raise ShareTokenInvalidError("Invalid or expired share link")

    if inv.acknowledged_at is None:
        now = datetime.now(tz=UTC)
        inv.acknowledged_at = now
        inv.acknowledged_by_name = customer_name
        inv.updated_at = now
        inv.version += 1
        await db.flush()

        log.info(
            "invoice.acknowledged",
            invoice_id=inv.id,
            customer_name=customer_name,
            ip_address=ip_address,
        )

    return inv
