"""AI orchestrator — runs the Claude tool-use loop with SSE streaming.

Flow:
1. Load conversation history from DB
2. Build messages list
3. Call Claude with streaming=True + tool definitions
4. For each streamed event:
   - text delta → yield SSE text event
   - tool_use block → execute tool, yield tool_call event
   - If mutation tool → check confirmed flag first
5. After Claude finishes → append assistant + tool_result messages to DB
6. Yield final "done" SSE event
"""
from __future__ import annotations

import json
import uuid
from collections.abc import AsyncGenerator
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.prompts import SYSTEM_PROMPT, SYSTEM_PROMPT_VERSION
from app.ai.tools.draft_handlers import DRAFT_HANDLERS, handle_post_journal_entry
from app.ai.tools.read_handlers import dispatch as read_dispatch
from app.ai.tools.registry import ALL_TOOLS, MUTATION_TOOL_NAMES
from app.core.config import get_settings
from app.infra.models import AiConversation, AiMessage

settings = get_settings()

MAX_HISTORY_MESSAGES = 20  # keep last N messages for context window management


def _get_client() -> Any:
    """Return an AsyncAnthropic client, or None if no API key is configured."""
    if not settings.anthropic_api_key:
        return None
    import anthropic  # lazy import so app starts without the package installed
    return anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)


async def get_or_create_conversation(
    db: AsyncSession,
    *,
    tenant_id: str,
    user_id: str,
    conversation_id: str | None,
) -> AiConversation:
    if conversation_id:
        result = await db.execute(
            select(AiConversation).where(
                AiConversation.id == conversation_id,
                AiConversation.tenant_id == tenant_id,
            )
        )
        conv = result.scalar_one_or_none()
        if conv:
            return conv
    conv = AiConversation(
        id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        user_id=user_id,
        title="New conversation",
        version=1,
        created_by=user_id,
        updated_by=user_id,
    )
    db.add(conv)
    await db.flush()
    return conv


async def load_history(
    db: AsyncSession, conversation_id: str
) -> list[dict[str, Any]]:
    result = await db.execute(
        select(AiMessage)
        .where(AiMessage.conversation_id == conversation_id)
        .order_by(AiMessage.created_at.asc())
        .limit(MAX_HISTORY_MESSAGES)
    )
    messages = result.scalars().all()

    history: list[dict[str, Any]] = []
    for msg in messages:
        if msg.role == "user":
            history.append({"role": "user", "content": msg.content or ""})
        elif msg.role == "assistant":
            if msg.tool_calls:
                content: list[dict[str, Any]] = []
                if msg.content:
                    content.append({"type": "text", "text": msg.content})
                for tc in msg.tool_calls:
                    content.append(tc)
                history.append({"role": "assistant", "content": content})
            else:
                history.append({"role": "assistant", "content": msg.content or ""})
        elif msg.role == "tool_result" and msg.tool_use_id:
            # Tool results are appended as user messages with tool_result content
            if history and history[-1]["role"] == "user" and isinstance(history[-1]["content"], list):
                history[-1]["content"].append(
                    {
                        "type": "tool_result",
                        "tool_use_id": msg.tool_use_id,
                        "content": msg.content or "",
                    }
                )
            else:
                history.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": msg.tool_use_id,
                                "content": msg.content or "",
                            }
                        ],
                    }
                )
    return history


async def run_chat(
    db: AsyncSession,
    *,
    tenant_id: str,
    user_id: str,
    user_message: str,
    conversation_id: str | None = None,
    confirmed_draft_id: str | None = None,
) -> AsyncGenerator[str, None]:
    """
    Main entry point. Yields SSE-formatted strings.

    SSE event types:
      data: {"type": "text", "delta": "..."}
      data: {"type": "tool_call", "name": "...", "result": {...}}
      data: {"type": "confirmation_required", "draft_id": "...", "proposed_entry": {...}}
      data: {"type": "conversation_id", "id": "..."}
      data: {"type": "done"}
      data: {"type": "error", "message": "..."}
    """
    try:
        client = _get_client()

        # Get or create conversation
        conv = await get_or_create_conversation(
            db, tenant_id=tenant_id, user_id=user_id, conversation_id=conversation_id
        )

        yield f"data: {json.dumps({'type': 'conversation_id', 'id': conv.id})}\n\n"

        # Load history + append new user message
        history = await load_history(db, conv.id)
        history.append({"role": "user", "content": user_message})

        # Persist user message
        user_msg = AiMessage(
            id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            conversation_id=conv.id,
            role="user",
            content=user_message,
            version=1,
            created_by=user_id,
            updated_by=user_id,
        )
        db.add(user_msg)

        # Update conversation title from first user message
        if conv.title == "New conversation":
            conv.title = user_message[:80]
            conv.updated_by = user_id

        await db.flush()

        # If no API key, return a helpful message without calling Claude
        if not client:
            no_key_msg = AiMessage(
                id=str(uuid.uuid4()),
                tenant_id=tenant_id,
                conversation_id=conv.id,
                role="assistant",
                content=(
                    "The AI assistant is not configured. "
                    "Please set the ANTHROPIC_API_KEY environment variable to enable it."
                ),
                version=1,
                created_by=user_id,
                updated_by=user_id,
            )
            db.add(no_key_msg)
            await db.commit()
            yield f"data: {json.dumps({'type': 'text', 'delta': no_key_msg.content})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
            return

        # Run the Claude tool-use loop
        accumulated_text = ""
        tool_uses: list[dict[str, Any]] = []
        tool_results: list[dict[str, Any]] = []
        input_tokens = output_tokens = cache_create = cache_read = 0

        current_messages = list(history)

        while True:
            # Call Claude with streaming
            async with client.messages.stream(
                model="claude-sonnet-4-6",
                max_tokens=4096,
                system=[
                    {
                        "type": "text",
                        "text": SYSTEM_PROMPT,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                tools=ALL_TOOLS,  # type: ignore[arg-type]
                messages=current_messages,
            ) as stream:
                current_tool_use: dict[str, Any] | None = None
                current_tool_input_str = ""

                async for event in stream:
                    etype = event.type  # type: ignore[union-attr]

                    if etype == "content_block_start":
                        block = event.content_block  # type: ignore[attr-defined]
                        if block.type == "tool_use":
                            current_tool_use = {
                                "id": block.id,
                                "name": block.name,
                                "type": "tool_use",
                            }
                            current_tool_input_str = ""

                    elif etype == "content_block_delta":
                        delta = event.delta  # type: ignore[attr-defined]
                        if delta.type == "text_delta":
                            accumulated_text += delta.text
                            yield f"data: {json.dumps({'type': 'text', 'delta': delta.text})}\n\n"
                        elif delta.type == "input_json_delta" and current_tool_use:
                            current_tool_input_str += delta.partial_json

                    elif etype == "content_block_stop" and current_tool_use:
                        # Tool use block complete — parse input and execute
                        try:
                            tool_input = (
                                json.loads(current_tool_input_str)
                                if current_tool_input_str
                                else {}
                            )
                        except json.JSONDecodeError:
                            tool_input = {}

                        current_tool_use["input"] = tool_input
                        tool_uses.append(dict(current_tool_use))

                        tool_name = current_tool_use["name"]
                        tool_use_id = current_tool_use["id"]

                        # Execute tool
                        if tool_name in MUTATION_TOOL_NAMES:
                            if tool_name == "post_journal_entry":
                                draft_id = tool_input.get("draft_id", "")
                                is_confirmed = confirmed_draft_id == draft_id
                                result = await handle_post_journal_entry(
                                    db, tenant_id, tool_input, confirmed=is_confirmed
                                )
                                if result.get("confirmation_required"):
                                    yield f"data: {json.dumps({'type': 'confirmation_required', 'draft_id': draft_id})}\n\n"
                            else:
                                result = {"error": f"Unknown mutation tool: {tool_name}"}
                        elif tool_name in DRAFT_HANDLERS:
                            result = await DRAFT_HANDLERS[tool_name](db, tenant_id, tool_input)
                            if (
                                result.get("confirmation_required")
                                and tool_name == "draft_journal_entry"
                            ):
                                yield f"data: {json.dumps({'type': 'confirmation_required', 'draft_id': result['draft_id'], 'proposed_entry': result['proposed_entry']})}\n\n"
                        else:
                            result = await read_dispatch(db, tenant_id, tool_name, tool_input)

                        yield f"data: {json.dumps({'type': 'tool_call', 'name': tool_name, 'result': result})}\n\n"

                        tool_results.append(
                            {
                                "type": "tool_result",
                                "tool_use_id": tool_use_id,
                                "content": json.dumps(result),
                            }
                        )

                        current_tool_use = None
                        current_tool_input_str = ""

                    elif etype == "message_delta":
                        usage = getattr(event, "usage", None)  # type: ignore[attr-defined]
                        if usage:
                            output_tokens += getattr(usage, "output_tokens", 0)

                    elif etype == "message_start":
                        msg_obj = event.message  # type: ignore[attr-defined]
                        usage = getattr(msg_obj, "usage", None)
                        if usage:
                            input_tokens += getattr(usage, "input_tokens", 0)
                            cache_create += getattr(usage, "cache_creation_input_tokens", 0)
                            cache_read += getattr(usage, "cache_read_input_tokens", 0)

            # After streaming ends
            final_msg = await stream.get_final_message()
            stop_reason = final_msg.stop_reason

            if stop_reason == "tool_use" and tool_results:
                # Build assistant message with tool uses + send tool results back
                assistant_content: list[dict[str, Any]] = []
                if accumulated_text:
                    assistant_content.append({"type": "text", "text": accumulated_text})
                assistant_content.extend(tool_uses)

                current_messages = current_messages + [
                    {"role": "assistant", "content": assistant_content},
                    {"role": "user", "content": tool_results},
                ]

                # Reset for next loop iteration
                accumulated_text = ""
                tool_uses = []
                tool_results = []
            else:
                # End of conversation turn
                break

        # Persist final assistant message
        asst_msg = AiMessage(
            id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            conversation_id=conv.id,
            role="assistant",
            content=accumulated_text,
            tool_calls=tool_uses if tool_uses else None,
            model="claude-sonnet-4-6",
            prompt_version=SYSTEM_PROMPT_VERSION,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_creation_tokens=cache_create,
            cache_read_tokens=cache_read,
            version=1,
            created_by=user_id,
            updated_by=user_id,
        )
        db.add(asst_msg)
        await db.commit()

        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    except Exception as e:
        await db.rollback()
        yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
