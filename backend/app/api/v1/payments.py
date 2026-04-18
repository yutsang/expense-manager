"""Payments API."""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, Query, Response, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from app.api.v1.deps import ActorId, DbSession, TenantId
from app.api.v1.schemas import (
    CsvImportResult,
    PaymentAllocationCreate,
    PaymentAllocationResponse,
    PaymentCreate,
    PaymentListResponse,
    PaymentResponse,
    PaymentVoidRequest,
)
from app.infra.models import Contact
from app.services.csv_import import generate_template_csv, parse_csv, parse_date, parse_decimal
from app.services.payments import (
    AllocationError,
    PaymentNotFoundError,
    PaymentTransitionError,
    allocate_payment,
    create_payment,
    get_payment,
    list_payments,
    void_payment,
)

router = APIRouter(prefix="/payments", tags=["payments"])


def _payment_response(payment) -> PaymentResponse:  # type: ignore[no-untyped-def]
    return PaymentResponse.model_validate(payment)


@router.post("", response_model=PaymentResponse, status_code=status.HTTP_201_CREATED)
async def create(
    body: PaymentCreate,
    db: DbSession,
    tenant_id: TenantId,
    actor_id: ActorId,
    response: Response,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> PaymentResponse:
    try:
        payment = await create_payment(
            db,
            tenant_id,
            actor_id,
            payment_type=body.payment_type,
            contact_id=body.contact_id,
            amount=Decimal(body.amount),
            currency=body.currency,
            fx_rate=Decimal(body.fx_rate),
            payment_date=body.payment_date,
            reference=body.reference,
            bank_account_ref=body.bank_account_ref,
            idempotency_key=idempotency_key,
        )
        await db.commit()
        await db.refresh(payment)
        # If idempotent hit, the payment already existed — return 200 instead of 201
        if (
            idempotency_key is not None
            and payment.idempotency_key == idempotency_key
            and not db.new
        ):
            response.status_code = status.HTTP_200_OK
        return _payment_response(payment)
    except (ValueError, AllocationError) as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.get("", response_model=PaymentListResponse)
async def list_all(
    db: DbSession,
    tenant_id: TenantId,
    payment_type: str | None = Query(default=None),
    pay_status: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
) -> PaymentListResponse:
    payments, total = await list_payments(
        db,
        tenant_id,
        limit=limit,
        offset=offset,
        payment_type=payment_type,
        status=pay_status,
    )
    return PaymentListResponse(
        items=[_payment_response(p) for p in payments],
        total=total,
    )


@router.get("/{payment_id}", response_model=PaymentResponse)
async def get_one(payment_id: str, db: DbSession, tenant_id: TenantId) -> PaymentResponse:
    try:
        payment = await get_payment(db, tenant_id, payment_id)
        return _payment_response(payment)
    except PaymentNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Payment not found")


@router.post(
    "/{payment_id}/allocate",
    response_model=PaymentAllocationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def allocate(
    payment_id: str,
    body: PaymentAllocationCreate,
    db: DbSession,
    tenant_id: TenantId,
    actor_id: ActorId,
) -> PaymentAllocationResponse:
    try:
        allocation = await allocate_payment(
            db,
            tenant_id,
            actor_id,
            payment_id=payment_id,
            invoice_id=body.invoice_id,
            bill_id=body.bill_id,
            amount_applied=Decimal(body.amount_applied),
        )
        await db.commit()
        await db.refresh(allocation)
        return PaymentAllocationResponse.model_validate(allocation)
    except PaymentNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Payment not found")
    except (AllocationError, PaymentTransitionError) as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))


@router.post("/{payment_id}/void", response_model=PaymentResponse)
async def void(
    payment_id: str,
    body: PaymentVoidRequest,
    db: DbSession,
    tenant_id: TenantId,
    actor_id: ActorId,
) -> PaymentResponse:
    try:
        payment = await void_payment(
            db,
            tenant_id,
            actor_id,
            payment_id=payment_id,
            reason=body.reason,
        )
        await db.commit()
        await db.refresh(payment)
        return _payment_response(payment)
    except PaymentNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Payment not found")
    except PaymentTransitionError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))


# ── CSV Import / Template ────────────────────────────────────────────────────

_PAYMENT_REQUIRED = ["payment_type", "contact_name_or_code", "amount", "payment_date"]
_PAYMENT_OPTIONAL = ["currency", "reference", "invoice_number", "bill_number"]
_PAYMENT_ALL = _PAYMENT_REQUIRED + _PAYMENT_OPTIONAL
_PAYMENT_EXAMPLE = [
    "received",
    "Acme Corp",
    "1000.00",
    "2025-01-20",
    "USD",
    "PAY-001",
    "INV-001",
    "",
]


@router.get("/csv-template")
async def csv_template() -> StreamingResponse:
    """Download a CSV template for payment imports."""
    content = generate_template_csv(_PAYMENT_ALL, _PAYMENT_EXAMPLE)
    return StreamingResponse(
        iter([content]),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="payments-template.csv"'},
    )


@router.post("/import", response_model=CsvImportResult, status_code=status.HTTP_201_CREATED)
async def import_payments(
    file: UploadFile,
    db: DbSession,
    tenant_id: TenantId,
    actor_id: ActorId,
) -> CsvImportResult:
    """Import payments from a CSV file."""
    content = await file.read()
    rows, errors = await parse_csv(content, _PAYMENT_REQUIRED, _PAYMENT_OPTIONAL)

    if errors and not rows:
        return CsvImportResult(imported=0, skipped=0, errors=errors)

    # Resolve contacts: name or code -> id
    contact_result = await db.execute(
        select(Contact.id, Contact.name, Contact.code).where(
            Contact.tenant_id == tenant_id, Contact.is_archived.is_(False)
        )
    )
    contact_map: dict[str, str] = {}
    for cid, cname, ccode in contact_result:
        contact_map[cname.lower()] = cid
        if ccode:
            contact_map[ccode.lower()] = cid

    imported = 0
    skipped = 0

    for row_no, row in enumerate(rows, start=2 + len(errors)):
        try:
            contact_key = row["contact_name_or_code"].lower()
            contact_id = contact_map.get(contact_key)
            if not contact_id:
                errors.append(f"Row {row_no}: contact '{row['contact_name_or_code']}' not found")
                skipped += 1
                continue

            payment_type = row["payment_type"].lower()
            if payment_type not in ("received", "made"):
                errors.append(
                    f"Row {row_no}: payment_type must be 'received' or 'made', got '{payment_type}'"
                )
                skipped += 1
                continue

            amount = parse_decimal(row["amount"])
            parsed_date = parse_date(row["payment_date"])
            currency = row.get("currency") or "USD"
            reference = row.get("reference") or None

            await create_payment(
                db,
                tenant_id,
                actor_id,
                payment_type=payment_type,
                contact_id=contact_id,
                amount=amount,
                currency=currency,
                payment_date=str(parsed_date),
                reference=reference,
            )
            imported += 1
        except Exception as exc:
            errors.append(f"Row {row_no}: {exc}")
            skipped += 1

    if imported > 0:
        await db.commit()

    from app.core.logging import get_logger

    get_logger(__name__).info(
        "payments.import.complete",
        tenant_id=tenant_id,
        imported=imported,
        skipped=skipped,
        errors=len(errors),
    )
    return CsvImportResult(imported=imported, skipped=skipped, errors=errors)
