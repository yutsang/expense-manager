"""Receipts API — upload, OCR via Claude Vision, list, get, delete."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, UploadFile, status

from app.api.v1.deps import ActorId, DbSession, TenantId
from app.api.v1.schemas import ReceiptResponse
from app.services.receipts import (
    ReceiptNotFoundError,
    delete_receipt,
    get_receipt,
    list_receipts,
    run_ocr,
    upload_receipt,
)

router = APIRouter(prefix="/receipts", tags=["receipts"])

_ALLOWED_TYPES = {
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/gif",
    "image/webp",
    "application/pdf",
}
_MAX_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB


@router.post("", response_model=ReceiptResponse, status_code=status.HTTP_201_CREATED)
async def create_receipt(
    file: UploadFile,
    db: DbSession,
    tenant_id: TenantId,
    actor_id: ActorId,
) -> ReceiptResponse:
    """Upload a receipt image and run OCR synchronously."""
    content_type = file.content_type or "application/octet-stream"
    if content_type not in _ALLOWED_TYPES:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unsupported file type: {content_type}. Allowed: {', '.join(sorted(_ALLOWED_TYPES))}",
        )

    file_bytes = await file.read()
    if len(file_bytes) > _MAX_SIZE_BYTES:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="File too large. Maximum size is 10 MB.",
        )

    receipt = await upload_receipt(
        db,
        tenant_id=tenant_id,
        actor_id=actor_id,
        filename=file.filename or "receipt",
        content_type=content_type,
        file_bytes=file_bytes,
    )
    await db.commit()
    await db.refresh(receipt)

    # Run OCR synchronously (fast with Haiku)
    try:
        receipt = await run_ocr(db, receipt_id=receipt.id, tenant_id=tenant_id)
        await db.commit()
        await db.refresh(receipt)
    except Exception:
        # OCR failure does not block upload — receipt is left with status=failed
        await db.commit()
        await db.refresh(receipt)

    return ReceiptResponse.model_validate(receipt)


@router.get("", response_model=list[ReceiptResponse])
async def list_all(
    db: DbSession,
    tenant_id: TenantId,
) -> list[ReceiptResponse]:
    """List the latest 50 receipts for the tenant."""
    receipts = await list_receipts(db, tenant_id)
    return [ReceiptResponse.model_validate(r) for r in receipts]


@router.get("/{receipt_id}", response_model=ReceiptResponse)
async def get_one(
    receipt_id: str,
    db: DbSession,
    tenant_id: TenantId,
) -> ReceiptResponse:
    try:
        receipt = await get_receipt(db, tenant_id, receipt_id)
        return ReceiptResponse.model_validate(receipt)
    except ReceiptNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Receipt not found")


@router.delete("/{receipt_id}", status_code=status.HTTP_204_NO_CONTENT)
async def soft_delete(
    receipt_id: str,
    db: DbSession,
    tenant_id: TenantId,
) -> None:
    try:
        await delete_receipt(db, tenant_id, receipt_id)
        await db.commit()
    except ReceiptNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Receipt not found")
