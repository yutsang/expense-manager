"""AI orchestrator — runs the DeepSeek tool-use loop with SSE streaming.

Uses the OpenAI-compatible DeepSeek API (model: deepseek-chat).

Flow:
1. Load conversation history from DB
2. Build messages list
3. Call DeepSeek with stream=True + function definitions
4. For each streamed chunk:
   - text delta → yield SSE text event
   - tool_call chunk → accumulate, then execute on finish
   - If mutation tool → check confirmed flag first
5. After model finishes → persist messages, yield "done"
"""
from __future__ import annotations

import json
import uuid
from collections.abc import AsyncGenerator
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.context import build_tenant_context
from app.ai.prompts import SYSTEM_PROMPT, SYSTEM_PROMPT_VERSION
from app.ai.tools.draft_handlers import DRAFT_HANDLERS, handle_post_journal_entry
from app.ai.tools.read_handlers import dispatch as read_dispatch
from app.ai.tools.registry import ALL_TOOLS_OPENAI, MUTATION_TOOL_NAMES
from app.core.config import get_settings
from app.infra.models import AiConversation, AiMessage

settings = get_settings()

DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-chat"
MAX_HISTORY_MESSAGES = 20


def _get_client() -> Any:
    """Return an AsyncOpenAI client pointed at DeepSeek, or None if no key."""
    if not settings.deepseek_api_key:
        return None
    from openai import AsyncOpenAI  # lazy import
    return AsyncOpenAI(api_key=settings.deepseek_api_key, base_url=DEEPSEEK_BASE_URL)


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
                history.append({"role": "assistant", "content": msg.content or "", "tool_calls": msg.tool_calls})
            else:
                history.append({"role": "assistant", "content": msg.content or ""})
        elif msg.role == "tool_result" and msg.tool_use_id:
            history.append({
                "role": "tool",
                "tool_call_id": msg.tool_use_id,
                "content": msg.content or "",
            })
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

        conv = await get_or_create_conversation(
            db, tenant_id=tenant_id, user_id=user_id, conversation_id=conversation_id
        )

        yield f"data: {json.dumps({'type': 'conversation_id', 'id': conv.id})}\n\n"

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

        if conv.title == "New conversation":
            conv.title = user_message[:80]
            conv.updated_by = user_id

        await db.flush()

        if not client:
            no_key_msg = AiMessage(
                id=str(uuid.uuid4()),
                tenant_id=tenant_id,
                conversation_id=conv.id,
                role="assistant",
                content=(
                    "The AI assistant is not configured. "
                    "Please set the DEEPSEEK_API_KEY environment variable to enable it."
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

        # System message
        system_message = {"role": "system", "content": SYSTEM_PROMPT}

        # Tenant context block (cached 5 min) — prepended before history
        tenant_ctx = await build_tenant_context(db, tenant_id)
        ctx_injection: list[dict[str, Any]] = [
            {"role": "user", "content": f"<tenant_context>\n{tenant_ctx}\n</tenant_context>"},
            {"role": "assistant", "content": "Understood. I have your account context loaded."},
        ]

        accumulated_text = ""
        persisted_tool_calls: list[dict[str, Any]] = []
        input_tokens = output_tokens = 0

        current_messages = [system_message] + ctx_injection + list(history)

        while True:
            stream = await client.chat.completions.create(
                model=DEEPSEEK_MODEL,
                messages=current_messages,  # type: ignore[arg-type]
                tools=ALL_TOOLS_OPENAI,  # type: ignore[arg-type]
                tool_choice="auto",
                stream=True,
            )

            # Accumulate tool call deltas: {index: {id, name, arguments_str}}
            tool_call_accum: dict[int, dict[str, Any]] = {}
            finish_reason: str | None = None

            async for chunk in stream:
                choice = chunk.choices[0] if chunk.choices else None
                if not choice:
                    continue

                finish_reason = choice.finish_reason or finish_reason
                delta = choice.delta

                # Text delta
                if delta.content:
                    accumulated_text += delta.content
                    yield f"data: {json.dumps({'type': 'text', 'delta': delta.content})}\n\n"

                # Tool call delta
                if delta.tool_calls:
                    for tc_delta in delta.tool_calls:
                        idx = tc_delta.index
                        if idx not in tool_call_accum:
                            tool_call_accum[idx] = {
                                "id": tc_delta.id or "",
                                "name": (tc_delta.function.name or "") if tc_delta.function else "",
                                "arguments_str": "",
                            }
                        if tc_delta.id:
                            tool_call_accum[idx]["id"] = tc_delta.id
                        if tc_delta.function:
                            if tc_delta.function.name:
                                tool_call_accum[idx]["name"] = tc_delta.function.name
                            if tc_delta.function.arguments:
                                tool_call_accum[idx]["arguments_str"] += tc_delta.function.arguments

                # Usage (some providers send in last chunk)
                if chunk.usage:
                    input_tokens += chunk.usage.prompt_tokens or 0
                    output_tokens += chunk.usage.completion_tokens or 0

            # Process completed tool calls
            if finish_reason == "tool_calls" and tool_call_accum:
                # Build OpenAI-style tool_calls list for the assistant message
                openai_tool_calls = []
                tool_results_messages = []

                for idx in sorted(tool_call_accum.keys()):
                    tc = tool_call_accum[idx]
                    tool_name = tc["name"]
                    tool_use_id = tc["id"] or str(uuid.uuid4())
                    try:
                        tool_input = json.loads(tc["arguments_str"]) if tc["arguments_str"] else {}
                    except json.JSONDecodeError:
                        tool_input = {}

                    openai_tool_calls.append({
                        "id": tool_use_id,
                        "type": "function",
                        "function": {
                            "name": tool_name,
                            "arguments": json.dumps(tool_input),
                        },
                    })

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
                        if result.get("confirmation_required") and tool_name == "draft_journal_entry":
                            yield f"data: {json.dumps({'type': 'confirmation_required', 'draft_id': result['draft_id'], 'proposed_entry': result['proposed_entry']})}\n\n"
                    else:
                        result = await read_dispatch(db, tenant_id, tool_name, tool_input)

                    yield f"data: {json.dumps({'type': 'tool_call', 'name': tool_name, 'result': result})}\n\n"

                    tool_results_messages.append({
                        "role": "tool",
                        "tool_call_id": tool_use_id,
                        "content": json.dumps(result),
                    })

                    persisted_tool_calls.append({
                        "id": tool_use_id,
                        "type": "function",
                        "function": {"name": tool_name, "arguments": json.dumps(tool_input)},
                    })

                # Append assistant message with tool calls + tool results, then loop
                current_messages = current_messages + [
                    {
                        "role": "assistant",
                        "content": accumulated_text or None,
                        "tool_calls": openai_tool_calls,
                    },
                ] + tool_results_messages

                accumulated_text = ""
            else:
                # End of turn
                break

        # Persist final assistant message
        asst_msg = AiMessage(
            id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            conversation_id=conv.id,
            role="assistant",
            content=accumulated_text,
            tool_calls=persisted_tool_calls if persisted_tool_calls else None,
            model=DEEPSEEK_MODEL,
            prompt_version=SYSTEM_PROMPT_VERSION,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
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
