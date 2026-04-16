"""Receipt service — upload to S3, run Claude Vision OCR."""

from __future__ import annotations

import base64
import json
import uuid
from datetime import UTC, datetime

import boto3
from anthropic import AsyncAnthropic
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.infra.models import Receipt

log = get_logger(__name__)
settings = get_settings()


class ReceiptNotFoundError(ValueError):
    pass


def _s3_client() -> object:
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url or None,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        region_name=settings.s3_region,
    )


async def upload_receipt(
    db: AsyncSession,
    *,
    tenant_id: str,
    actor_id: str | None,
    filename: str,
    content_type: str,
    file_bytes: bytes,
) -> Receipt:
    """Store file to S3 and create a Receipt DB record with status=pending."""
    receipt_id = str(uuid.uuid4())
    s3_key = f"receipts/{tenant_id}/{receipt_id}/{filename}"
    file_size_kb = max(1, len(file_bytes) // 1024)

    # Upload to S3
    s3 = _s3_client()
    s3.put_object(  # type: ignore[union-attr]
        Bucket=settings.s3_bucket_documents,
        Key=s3_key,
        Body=file_bytes,
        ContentType=content_type,
    )
    log.info("receipt.uploaded_to_s3", tenant_id=tenant_id, s3_key=s3_key)

    receipt = Receipt(
        id=receipt_id,
        tenant_id=tenant_id,
        filename=filename,
        s3_key=s3_key,
        content_type=content_type,
        file_size_kb=file_size_kb,
        status="pending",
        created_by=actor_id,
    )
    db.add(receipt)
    await db.flush()
    await db.refresh(receipt)
    return receipt


async def run_ocr(
    db: AsyncSession,
    *,
    receipt_id: str,
    tenant_id: str,
) -> Receipt:
    """Call Claude Vision on the receipt image, parse response, update receipt."""
    receipt = await db.scalar(
        select(Receipt).where(
            Receipt.id == receipt_id,
            Receipt.tenant_id == tenant_id,
        )
    )
    if not receipt:
        raise ReceiptNotFoundError(receipt_id)

    receipt.status = "processing"
    receipt.updated_at = datetime.now(tz=UTC)
    await db.flush()

    try:
        # Download file bytes from S3
        s3 = _s3_client()
        response = s3.get_object(Bucket=settings.s3_bucket_documents, Key=receipt.s3_key)  # type: ignore[union-attr]
        file_bytes: bytes = response["Body"].read()

        b64_data = base64.standard_b64encode(file_bytes).decode("utf-8")

        client = AsyncAnthropic()
        message = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            system=(
                "You are a receipt parser. Extract structured data from the receipt image provided. "
                "Return ONLY valid JSON with these fields: "
                '{"vendor": string|null, "date": "YYYY-MM-DD"|null, "currency": "ISO-4217-code"|null, '
                '"total": number|null, "line_items": [{"description": string|null, "quantity": number|null, '
                '"unit_price": number|null, "amount": number|null}]}. '
                "Return null for any field you cannot confidently determine. "
                "Do not include any text outside the JSON object."
            ),
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": receipt.content_type,  # type: ignore[dict-item]
                                "data": b64_data,
                            },
                        },
                        {
                            "type": "text",
                            "text": "Please extract the receipt data and return JSON only.",
                        },
                    ],
                }
            ],
        )

        raw_text = message.content[0].text if message.content else ""
        log.info("receipt.ocr_raw_response", receipt_id=receipt_id, length=len(raw_text))

        # Parse the JSON response gracefully
        parsed: dict = {}
        try:
            # Strip any markdown code fences if present
            clean = raw_text.strip()
            if clean.startswith("```"):
                lines = clean.split("\n")
                clean = "\n".join(lines[1:-1]) if len(lines) > 2 else clean
            parsed = json.loads(clean)
        except (json.JSONDecodeError, ValueError):
            log.warning("receipt.ocr_parse_failed", receipt_id=receipt_id, raw=raw_text[:200])
            parsed = {}

        from decimal import Decimal, InvalidOperation

        ocr_total_val = None
        raw_total = parsed.get("total")
        if raw_total is not None:
            try:
                ocr_total_val = Decimal(str(raw_total))
            except InvalidOperation:
                ocr_total_val = None

        receipt.ocr_vendor = parsed.get("vendor")
        receipt.ocr_date = parsed.get("date")
        receipt.ocr_currency = parsed.get("currency")
        receipt.ocr_total = ocr_total_val
        receipt.ocr_raw = parsed
        receipt.status = "done"
        receipt.updated_at = datetime.now(tz=UTC)

        log.info(
            "receipt.ocr_done",
            receipt_id=receipt_id,
            vendor=receipt.ocr_vendor,
            total=str(ocr_total_val),
        )

    except Exception as exc:
        log.error("receipt.ocr_error", receipt_id=receipt_id, error=str(exc))
        receipt.status = "failed"
        receipt.updated_at = datetime.now(tz=UTC)
        raise

    await db.flush()
    await db.refresh(receipt)
    return receipt


async def list_receipts(
    db: AsyncSession,
    tenant_id: str,
    *,
    limit: int = 50,
) -> list[Receipt]:
    result = await db.execute(
        select(Receipt)
        .where(
            Receipt.tenant_id == tenant_id,
            Receipt.status != "deleted",
        )
        .order_by(Receipt.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars())


async def get_receipt(db: AsyncSession, tenant_id: str, receipt_id: str) -> Receipt:
    receipt = await db.scalar(
        select(Receipt).where(
            Receipt.id == receipt_id,
            Receipt.tenant_id == tenant_id,
        )
    )
    if not receipt:
        raise ReceiptNotFoundError(receipt_id)
    return receipt


async def delete_receipt(
    db: AsyncSession,
    tenant_id: str,
    receipt_id: str,
) -> Receipt:
    receipt = await get_receipt(db, tenant_id, receipt_id)
    receipt.status = "deleted"
    receipt.updated_at = datetime.now(tz=UTC)
    await db.flush()
    await db.refresh(receipt)
    return receipt
