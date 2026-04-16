"""AI assistant API — SSE streaming chat endpoint."""
from __future__ import annotations

import uuid

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select

from app.ai.orchestrator import run_chat
from app.api.v1.deps import ActorId, DbSession, TenantId
from app.infra.models import AiConversation, AiMessage

router = APIRouter(tags=["ai"])


class ChatRequest(BaseModel):
    message: str
    conversation_id: uuid.UUID | None = None
    confirmed_draft_id: str | None = None  # set when user confirms a draft


@router.post("/ai/chat")
async def chat(
    body: ChatRequest,
    db: DbSession,
    tenant_id: TenantId,
    actor_id: ActorId,
) -> StreamingResponse:
    """Stream AI assistant responses as SSE."""
    # Fall back to a placeholder actor ID if auth is not yet wired
    effective_actor_id = actor_id or str(uuid.uuid4())

    async def generate() -> object:
        async for chunk in run_chat(
            db,
            tenant_id=tenant_id,
            user_id=effective_actor_id,
            user_message=body.message,
            conversation_id=str(body.conversation_id) if body.conversation_id else None,
            confirmed_draft_id=body.confirmed_draft_id,
        ):
            yield chunk

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/ai/conversations")
async def list_conversations(
    db: DbSession,
    tenant_id: TenantId,
) -> list[dict]:
    result = await db.execute(
        select(AiConversation)
        .where(AiConversation.tenant_id == tenant_id)
        .order_by(AiConversation.created_at.desc())
        .limit(50)
    )
    convs = result.scalars().all()
    return [
        {
            "id": str(c.id),
            "title": c.title,
            "created_at": c.created_at.isoformat(),
        }
        for c in convs
    ]


@router.get("/ai/conversations/{conversation_id}/messages")
async def get_messages(
    conversation_id: uuid.UUID,
    db: DbSession,
    tenant_id: TenantId,
) -> list[dict]:
    result = await db.execute(
        select(AiMessage)
        .where(
            AiMessage.conversation_id == str(conversation_id),
            AiMessage.tenant_id == tenant_id,
        )
        .order_by(AiMessage.created_at.asc())
    )
    msgs = result.scalars().all()
    return [
        {
            "id": str(m.id),
            "role": m.role,
            "content": m.content,
            "tool_calls": m.tool_calls,
            "created_at": m.created_at.isoformat(),
        }
        for m in msgs
    ]
