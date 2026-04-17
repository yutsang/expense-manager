"""Payments API."""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, Query, Response, status

from app.api.v1.deps import ActorId, DbSession, TenantId
from app.api.v1.schemas import (
    PaymentAllocationCreate,
    PaymentAllocationResponse,
    PaymentCreate,
    PaymentListResponse,
    PaymentResponse,
    PaymentVoidRequest,
)
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
