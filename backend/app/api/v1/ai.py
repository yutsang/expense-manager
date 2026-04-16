"""AI assistant API — SSE streaming chat endpoint."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select, text

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


@router.get("/ai/cost-summary")
async def cost_summary(
    db: DbSession,
    tenant_id: TenantId,
) -> dict:
    """Return token usage and message counts for this tenant.

    Provides today, this month, and a per-day breakdown for the last 30 days.
    """
    now = datetime.now(tz=UTC)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    thirty_days_ago = now - timedelta(days=30)

    # Today summary
    today_row = await db.execute(
        text("""
            SELECT
                COALESCE(SUM(input_tokens), 0)  AS input_tokens,
                COALESCE(SUM(output_tokens), 0) AS output_tokens,
                COUNT(*)                         AS messages
            FROM ai_messages
            WHERE tenant_id = :tid
              AND role = 'assistant'
              AND created_at >= :start
        """),
        {"tid": tenant_id, "start": today_start},
    )
    today_stats = today_row.fetchone()

    # Month summary
    month_row = await db.execute(
        text("""
            SELECT
                COALESCE(SUM(input_tokens), 0)  AS input_tokens,
                COALESCE(SUM(output_tokens), 0) AS output_tokens,
                COUNT(*)                         AS messages
            FROM ai_messages
            WHERE tenant_id = :tid
              AND role = 'assistant'
              AND created_at >= :start
        """),
        {"tid": tenant_id, "start": month_start},
    )
    month_stats = month_row.fetchone()

    # Per-day last 30 days
    daily_rows = await db.execute(
        text("""
            SELECT
                DATE(created_at AT TIME ZONE 'UTC') AS day,
                COALESCE(SUM(input_tokens), 0)      AS input_tokens,
                COALESCE(SUM(output_tokens), 0)     AS output_tokens
            FROM ai_messages
            WHERE tenant_id = :tid
              AND role = 'assistant'
              AND created_at >= :start
            GROUP BY day
            ORDER BY day DESC
        """),
        {"tid": tenant_id, "start": thirty_days_ago},
    )
    daily = daily_rows.fetchall()

    return {
        "today": {
            "input_tokens": int(today_stats.input_tokens),
            "output_tokens": int(today_stats.output_tokens),
            "messages": int(today_stats.messages),
        },
        "this_month": {
            "input_tokens": int(month_stats.input_tokens),
            "output_tokens": int(month_stats.output_tokens),
            "messages": int(month_stats.messages),
        },
        "by_day": [
            {
                "date": str(row.day),
                "input_tokens": int(row.input_tokens),
                "output_tokens": int(row.output_tokens),
            }
            for row in daily
        ],
    }
