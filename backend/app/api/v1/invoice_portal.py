"""Invoice portal API — shareable public invoice links (Issue #36).

Two sets of routes:
  1. Authenticated: POST /v1/invoices/{id}/share-link (generates token)
  2. Public (unauthenticated): GET /v1/public/invoices/{token}, POST .../acknowledge
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import ActorId, DbSession, TenantId, get_db
from app.api.v1.schemas import (
    InvoiceAcknowledgeRequest,
    InvoiceAcknowledgeResponse,
    PublicInvoiceResponse,
    ShareLinkResponse,
)
from app.services.invoice_portal import (
    InvoiceNotShareableError,
    ShareTokenInvalidError,
    acknowledge_invoice,
    generate_share_link,
    get_public_invoice_detail,
)
from app.services.invoices import InvoiceNotFoundError

# ── Authenticated routes (require tenant context) ───────────────────────────

router = APIRouter(tags=["invoice-portal"])


@router.post(
    "/invoices/{invoice_id}/share-link",
    response_model=ShareLinkResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_share_link(
    invoice_id: str,
    db: DbSession,
    tenant_id: TenantId,
    actor_id: ActorId,
):
    """Generate a public share link for an invoice."""
    try:
        result = await generate_share_link(db, tenant_id=tenant_id, invoice_id=invoice_id)
        await db.commit()
        return ShareLinkResponse(**result)
    except InvoiceNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")
    except InvoiceNotShareableError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# ── Public routes (no auth required) ────────────────────────────────────────

public_router = APIRouter(prefix="/public/invoices", tags=["invoice-portal-public"])


@public_router.get("/{token}", response_model=PublicInvoiceResponse)
async def get_public_invoice(
    token: str,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """View an invoice via its public share link. No authentication required."""
    try:
        detail = await get_public_invoice_detail(db, share_token=token)
        return PublicInvoiceResponse(**detail)
    except ShareTokenInvalidError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invoice not found or link has expired",
        )


@public_router.post("/{token}/acknowledge", response_model=InvoiceAcknowledgeResponse)
async def acknowledge(
    token: str,
    body: InvoiceAcknowledgeRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Customer acknowledges receipt of an invoice. No authentication required."""
    try:
        ip = request.client.host if request.client else None
        inv = await acknowledge_invoice(
            db,
            share_token=token,
            customer_name=body.customer_name,
            ip_address=ip,
        )
        await db.commit()
        return InvoiceAcknowledgeResponse(
            acknowledged_at=inv.acknowledged_at.isoformat() if inv.acknowledged_at else "",
            acknowledged_by_name=inv.acknowledged_by_name,
        )
    except ShareTokenInvalidError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invoice not found or link has expired",
        )
