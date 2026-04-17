"""Global search API — Cmd+K cross-entity search (Issue #39)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status

from app.api.v1.deps import DbSession, TenantId
from app.api.v1.schemas import SearchResponse, SearchResultItem
from app.services.search import SearchQueryTooShortError, global_search

router = APIRouter(prefix="/search", tags=["search"])


@router.get("", response_model=SearchResponse)
async def search(
    db: DbSession,
    tenant_id: TenantId,
    q: str = Query(..., min_length=1, description="Search query"),
    limit: int = Query(default=10, ge=1, le=50),
):
    """Search across contacts, invoices, bills, and journal entries."""
    try:
        results = await global_search(db, tenant_id=tenant_id, query=q, limit=limit)
        items = [SearchResultItem(**r) for r in results]
        return SearchResponse(query=q, items=items, total=len(items))
    except SearchQueryTooShortError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
