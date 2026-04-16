"""Attachments API — generic file uploads linked to any document type."""

from __future__ import annotations

import contextlib
from datetime import UTC, datetime

import boto3
from fastapi import APIRouter, HTTPException, Query, UploadFile, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy import select

from app.api.v1.deps import ActorId, DbSession, TenantId
from app.core.config import get_settings
from app.infra.models import Attachment

router = APIRouter(prefix="/attachments", tags=["attachments"])
settings = get_settings()

ALLOWED_ENTITY_TYPES = frozenset(
    {"invoice", "bill", "po", "sales_document", "payment", "journal_entry"}
)


# ── Schemas ────────────────────────────────────────────────────────────────────


class AttachmentOut(BaseModel):
    id: str
    entity_type: str
    entity_id: str
    filename: str
    content_type: str
    file_size_kb: int
    uploaded_by: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


# ── S3 helper ─────────────────────────────────────────────────────────────────


def _s3_client() -> object:
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url or None,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        region_name=settings.s3_region,
    )


# ── Routes ─────────────────────────────────────────────────────────────────────


@router.post("", response_model=AttachmentOut, status_code=status.HTTP_201_CREATED)
async def upload(
    entity_type: str,
    entity_id: str,
    file: UploadFile,
    db: DbSession,
    tenant_id: TenantId,
    actor_id: ActorId,
) -> AttachmentOut:
    if entity_type not in ALLOWED_ENTITY_TYPES:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"entity_type must be one of: {', '.join(sorted(ALLOWED_ENTITY_TYPES))}",
        )
    if not file.filename:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="filename is required")

    file_bytes = await file.read()
    file_size_kb = max(1, len(file_bytes) // 1024)
    content_type = file.content_type or "application/octet-stream"
    safe_filename = file.filename.replace(" ", "_")
    s3_key = f"attachments/{tenant_id}/{entity_type}/{entity_id}/{safe_filename}"

    s3 = _s3_client()
    s3.put_object(  # type: ignore[union-attr]
        Bucket=settings.s3_bucket_documents,
        Key=s3_key,
        Body=file_bytes,
        ContentType=content_type,
    )

    now = datetime.now(tz=UTC)
    att = Attachment(
        tenant_id=tenant_id,
        entity_type=entity_type,
        entity_id=entity_id,
        filename=safe_filename,
        s3_key=s3_key,
        content_type=content_type,
        file_size_kb=file_size_kb,
        uploaded_by=actor_id,
        created_at=now,
    )
    db.add(att)
    await db.commit()
    await db.refresh(att)
    return AttachmentOut.model_validate(att)


@router.get("", response_model=list[AttachmentOut])
async def list_attachments(
    db: DbSession,
    tenant_id: TenantId,
    entity_type: str = Query(...),
    entity_id: str = Query(...),
) -> list[AttachmentOut]:
    result = await db.execute(
        select(Attachment)
        .where(
            Attachment.tenant_id == tenant_id,
            Attachment.entity_type == entity_type,
            Attachment.entity_id == entity_id,
        )
        .order_by(Attachment.created_at)
    )
    atts = result.scalars().all()
    return [AttachmentOut.model_validate(a) for a in atts]


@router.get("/{attachment_id}/download")
async def download(attachment_id: str, db: DbSession, tenant_id: TenantId) -> RedirectResponse:
    result = await db.execute(
        select(Attachment).where(Attachment.id == attachment_id, Attachment.tenant_id == tenant_id)
    )
    att = result.scalar_one_or_none()
    if att is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Attachment not found")

    s3 = _s3_client()
    url = s3.generate_presigned_url(  # type: ignore[union-attr]
        "get_object",
        Params={"Bucket": settings.s3_bucket_documents, "Key": att.s3_key},
        ExpiresIn=300,
    )
    return RedirectResponse(url=url)


@router.delete("/{attachment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_attachment(attachment_id: str, db: DbSession, tenant_id: TenantId) -> None:
    result = await db.execute(
        select(Attachment).where(Attachment.id == attachment_id, Attachment.tenant_id == tenant_id)
    )
    att = result.scalar_one_or_none()
    if att is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Attachment not found")

    s3 = _s3_client()
    with contextlib.suppress(Exception):  # Best-effort S3 delete; DB record still removed
        s3.delete_object(  # type: ignore[union-attr]
            Bucket=settings.s3_bucket_documents, Key=att.s3_key
        )

    await db.delete(att)
    await db.commit()
