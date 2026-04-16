"""Contacts API — CRUD."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status

from app.api.v1.deps import ActorId, DbSession, TenantId
from app.api.v1.schemas import (
    ContactCreate,
    ContactListResponse,
    ContactResponse,
    ContactUpdate,
)
from app.services.contacts import (
    ContactCodeConflictError,
    ContactNotFoundError,
    archive_contact,
    create_contact,
    get_contact,
    list_contacts,
    update_contact,
)

router = APIRouter(prefix="/contacts", tags=["contacts"])


@router.post("", response_model=ContactResponse, status_code=status.HTTP_201_CREATED)
async def create(body: ContactCreate, db: DbSession, tenant_id: TenantId, actor_id: ActorId):
    try:
        contact = await create_contact(db, tenant_id, actor_id, **body.model_dump())
        await db.commit()
        return contact
    except ContactCodeConflictError as exc:
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
