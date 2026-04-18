"""Contacts API — CRUD + AMLO Cap 615 risk rating."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse

from app.api.v1.deps import ActorId, DbSession, TenantId
from app.api.v1.schemas import (
    ContactCreate,
    ContactListResponse,
    ContactResponse,
    ContactUpdate,
    CsvImportResult,
    RiskRatingUpdate,
)
from app.services.contacts import (
    ContactCodeConflictError,
    ContactNotFoundError,
    DuplicateContactError,
    EddNotRequiredError,
    approve_edd,
    archive_contact,
    create_contact,
    get_contact,
    list_contacts,
    set_risk_rating,
    update_contact,
)
from app.services.csv_import import generate_template_csv, parse_csv

router = APIRouter(prefix="/contacts", tags=["contacts"])


@router.post("", response_model=ContactResponse, status_code=status.HTTP_201_CREATED)
async def create(body: ContactCreate, db: DbSession, tenant_id: TenantId, actor_id: ActorId):
    try:
        contact = await create_contact(db, tenant_id, actor_id, **body.model_dump())
        await db.commit()
        return contact
    except ContactCodeConflictError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc))
    except DuplicateContactError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc))


@router.get("", response_model=ContactListResponse)
async def list_all(
    db: DbSession,
    tenant_id: TenantId,
    contact_type: str | None = Query(default=None),
    include_archived: bool = Query(default=False),
    limit: int = Query(default=50, le=200),
    cursor: str | None = Query(default=None),
):
    items = await list_contacts(
        db,
        tenant_id,
        contact_type=contact_type,
        include_archived=include_archived,
        limit=limit + 1,
        cursor=cursor,
    )
    next_cursor = None
    if len(items) > limit:
        next_cursor = items[limit].id
        items = items[:limit]
    return ContactListResponse(items=items, next_cursor=next_cursor)


# ── CSV Import / Template ────────────────────────────────────────────────────
# These MUST be registered before /{contact_id} to avoid path conflicts.

_CONTACT_REQUIRED = ["name", "contact_type"]
_CONTACT_OPTIONAL = [
    "code", "email", "phone", "currency", "tax_number",
    "address_line1", "city", "country", "credit_limit",
]
_CONTACT_ALL = _CONTACT_REQUIRED + _CONTACT_OPTIONAL
_CONTACT_EXAMPLE = [
    "Acme Corp", "customer", "ACME", "acme@example.com", "+1-555-0100",
    "USD", "12-345-678", "123 Main St", "New York", "US", "50000",
]


@router.get("/csv-template")
async def csv_template() -> StreamingResponse:
    """Download a CSV template for contact imports."""
    content = generate_template_csv(_CONTACT_ALL, _CONTACT_EXAMPLE)
    return StreamingResponse(
        iter([content]),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="contacts-template.csv"'},
    )


@router.post("/import", response_model=CsvImportResult, status_code=status.HTTP_201_CREATED)
async def import_contacts(
    file: UploadFile,
    db: DbSession,
    tenant_id: TenantId,
    actor_id: ActorId,
) -> CsvImportResult:
    """Import contacts from a CSV file."""
    content = await file.read()
    rows, errors = await parse_csv(content, _CONTACT_REQUIRED, _CONTACT_OPTIONAL)

    imported = 0
    skipped = 0

    for row_no, row in enumerate(rows, start=2 + len(errors)):
        try:
            await create_contact(
                db,
                tenant_id,
                actor_id,
                contact_type=row["contact_type"],
                name=row["name"],
                code=row.get("code") or None,
                email=row.get("email") or None,
                phone=row.get("phone") or None,
                currency=row.get("currency") or "USD",
                tax_number=row.get("tax_number") or None,
                address_line1=row.get("address_line1") or None,
                city=row.get("city") or None,
                country=row.get("country") or None,
                credit_limit=row.get("credit_limit") or None,
            )
            imported += 1
        except (ContactCodeConflictError, DuplicateContactError):
            skipped += 1
        except Exception as exc:
            errors.append(f"Row {row_no}: {exc}")
            skipped += 1

    if imported > 0:
        await db.commit()

    from app.core.logging import get_logger
    get_logger(__name__).info(
        "contacts.import.complete",
        tenant_id=tenant_id,
        imported=imported,
        skipped=skipped,
        errors=len(errors),
    )
    return CsvImportResult(imported=imported, skipped=skipped, errors=errors)


# ── Single-resource endpoints (parameterized paths) ──────────────────────────


@router.get("/{contact_id}", response_model=ContactResponse)
async def get_one(contact_id: str, db: DbSession, tenant_id: TenantId):
    try:
        return await get_contact(db, tenant_id, contact_id)
    except ContactNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Contact not found")


@router.patch("/{contact_id}", response_model=ContactResponse)
async def update(
    contact_id: str, body: ContactUpdate, db: DbSession, tenant_id: TenantId, actor_id: ActorId
):
    try:
        contact = await update_contact(
            db,
            tenant_id,
            contact_id,
            actor_id,
            {k: v for k, v in body.model_dump().items() if v is not None},
        )
        await db.commit()
        return contact
    except ContactNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Contact not found")


@router.delete("/{contact_id}", status_code=status.HTTP_204_NO_CONTENT)
async def archive(contact_id: str, db: DbSession, tenant_id: TenantId, actor_id: ActorId) -> None:
    try:
        await archive_contact(db, tenant_id, contact_id, actor_id)
        await db.commit()
    except ContactNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Contact not found")


@router.post("/{contact_id}/risk-rating", response_model=ContactResponse)
async def update_risk_rating(
    contact_id: str,
    body: RiskRatingUpdate,
    db: DbSession,
    tenant_id: TenantId,
    actor_id: ActorId,
):
    """Set AMLO Cap 615 risk rating for a contact (accountant+ role)."""
    try:
        contact = await set_risk_rating(
            db,
            tenant_id,
            contact_id,
            actor_id,
            risk_rating=body.risk_rating,
            risk_rating_rationale=body.risk_rating_rationale,
        )
        await db.commit()
        return contact
    except ContactNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Contact not found")


@router.post("/{contact_id}/edd-approve", response_model=ContactResponse)
async def edd_approve(
    contact_id: str,
    db: DbSession,
    tenant_id: TenantId,
    actor_id: ActorId,
):
    """Approve Enhanced Due Diligence for a high-risk contact."""
    try:
        contact = await approve_edd(db, tenant_id, contact_id, actor_id)
        await db.commit()
        return contact
    except ContactNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Contact not found")
    except EddNotRequiredError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc))
