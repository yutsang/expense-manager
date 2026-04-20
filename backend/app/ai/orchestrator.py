"""AI orchestrator — runs the Claude tool-use loop with SSE streaming.

Primary backend is Anthropic (Claude Sonnet 4.6 per CLAUDE.md §11.1) with
prompt caching enabled on the system prompt + tenant context block (CLAUDE.md
§11.2). If ``ANTHROPIC_API_KEY`` is not configured but ``DEEPSEEK_API_KEY``
is, the orchestrator falls back to the legacy DeepSeek path so existing
deployments keep working during rollout.

Flow (Anthropic path):
1. Load conversation history from DB
2. Build messages list
3. Call Anthropic with ``stream=True`` + tool definitions
4. For each streamed event:
   - text delta → yield SSE text event
   - tool_use complete → execute handler (mutation tools require confirmed flag)
5. Loop until no more tool calls, persist messages with cache metrics, yield ``done``
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
from app.ai.tools.registry import ALL_TOOLS, ALL_TOOLS_OPENAI, MUTATION_TOOL_NAMES
from app.core.config import get_settings
from app.infra.models import AiConversation, AiMessage

settings = get_settings()

MAX_HISTORY_MESSAGES = 20
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-chat"


def _get_anthropic_client() -> Any:
    if not settings.anthropic_api_key:
        return None
    from anthropic import AsyncAnthropic  # lazy import

    return AsyncAnthropic(api_key=settings.anthropic_api_key)


def _get_deepseek_client() -> Any:
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


async def _load_history_anthropic(db: AsyncSession, conversation_id: str) -> list[dict[str, Any]]:
    """Build Anthropic-format message history from persisted AiMessage rows."""
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
            blocks: list[dict[str, Any]] = []
            if msg.content:
                blocks.append({"type": "text", "text": msg.content})
            for tc in msg.tool_calls or []:
                # Stored in OpenAI-ish format ({id, function: {name, arguments}}); flatten.
                fn = tc.get("function", tc)
                args_str = fn.get("arguments") or "{}"
                try:
                    args = json.loads(args_str) if isinstance(args_str, str) else args_str
                except json.JSONDecodeError:
                    args = {}
                blocks.append(
                    {
                        "type": "tool_use",
                        "id": tc.get("id"),
                        "name": fn.get("name"),
                        "input": args,
                    }
                )
            history.append({"role": "assistant", "content": blocks or msg.content or ""})
        elif msg.role == "tool_result" and msg.tool_use_id:
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


async def _load_history_deepseek(db: AsyncSession, conversation_id: str) -> list[dict[str, Any]]:
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
                history.append(
                    {
                        "role": "assistant",
                        "content": msg.content or "",
                        "tool_calls": msg.tool_calls,
                    }
                )
            else:
                history.append({"role": "assistant", "content": msg.content or ""})
        elif msg.role == "tool_result" and msg.tool_use_id:
            history.append(
                {
                    "role": "tool",
                    "tool_call_id": msg.tool_use_id,
                    "content": msg.content or "",
                }
            )
    return history


async def _execute_tool(
    db: AsyncSession,
    *,
    tenant_id: str,
    tool_name: str,
    tool_input: dict[str, Any],
    confirmed_draft_id: str | None,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Run a tool handler. Returns (result, sse_side_event or None).

    ``sse_side_event`` carries ``confirmation_required`` metadata that the SSE
    stream should relay to the UI — it is not part of the tool result itself.
    """
    side: dict[str, Any] | None = None

    if tool_name in MUTATION_TOOL_NAMES:
        if tool_name == "post_journal_entry":
            draft_id = tool_input.get("draft_id", "")
            is_confirmed = confirmed_draft_id == draft_id
            result = await handle_post_journal_entry(
                db, tenant_id, tool_input, confirmed=is_confirmed
            )
            if result.get("confirmation_required"):
                side = {"type": "confirmation_required", "draft_id": draft_id}
        else:
            result = {"error": f"Unknown mutation tool: {tool_name}"}
    elif tool_name in DRAFT_HANDLERS:
        result = await DRAFT_HANDLERS[tool_name](db, tenant_id, tool_input)
        if result.get("confirmation_required") and tool_name == "draft_journal_entry":
            side = {
                "type": "confirmation_required",
                "draft_id": result["draft_id"],
                "proposed_entry": result["proposed_entry"],
            }
    else:
        result = await read_dispatch(db, tenant_id, tool_name, tool_input)

    return result, side


async def _run_anthropic(
    db: AsyncSession,
    client: Any,
    *,
    conv: AiConversation,
    tenant_id: str,
    user_id: str,
    user_message: str,
    confirmed_draft_id: str | None,
) -> AsyncGenerator[str, None]:
    """Anthropic path. Streams SSE events; persists final assistant message."""

    # Persist user message up front so conversation resumption works.
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

    history = await _load_history_anthropic(db, conv.id)
    history.append({"role": "user", "content": user_message})

    tenant_ctx = await build_tenant_context(db, tenant_id)

    # System prompt is a list of text blocks so we can mark cache control.
    system_blocks = [
        {
            "type": "text",
            "text": SYSTEM_PROMPT,
            "cache_control": {"type": "ephemeral"},
        },
        {
            "type": "text",
            "text": f"<tenant_context>\n{tenant_ctx}\n</tenant_context>",
            "cache_control": {"type": "ephemeral"},
        },
    ]

    total_input = total_output = 0
    total_cache_create = total_cache_read = 0
    persisted_tool_calls: list[dict[str, Any]] = []
    final_text = ""

    current_messages = list(history)
    max_iterations = 8  # safety cap on tool-use loops
    iteration = 0

    while iteration < max_iterations:
        iteration += 1

        async with client.messages.stream(
            model=settings.ai_model_default,
            max_tokens=4096,
            system=system_blocks,
            tools=ALL_TOOLS,
            messages=current_messages,
        ) as stream:
            accumulated_text = ""
            async for event in stream:
                et = getattr(event, "type", "")
                if et == "content_block_delta":
                    delta = getattr(event, "delta", None)
                    if delta is not None and getattr(delta, "type", "") == "text_delta":
                        text_chunk = getattr(delta, "text", "")
                        if text_chunk:
                            accumulated_text += text_chunk
                            yield (
                                "data: "
                                + json.dumps({"type": "text", "delta": text_chunk})
                                + "\n\n"
                            )

            final_message = await stream.get_final_message()

        # Tally usage (usage is on the final Message object).
        usage = getattr(final_message, "usage", None)
        if usage is not None:
            total_input += getattr(usage, "input_tokens", 0) or 0
            total_output += getattr(usage, "output_tokens", 0) or 0
            total_cache_create += getattr(usage, "cache_creation_input_tokens", 0) or 0
            total_cache_read += getattr(usage, "cache_read_input_tokens", 0) or 0

        # Partition the response into text + tool_use blocks.
        tool_uses: list[dict[str, Any]] = []
        assistant_blocks: list[dict[str, Any]] = []
        for block in final_message.content:
            bt = getattr(block, "type", "")
            if bt == "text":
                assistant_blocks.append({"type": "text", "text": getattr(block, "text", "")})
            elif bt == "tool_use":
                tu = {
                    "id": getattr(block, "id", ""),
                    "name": getattr(block, "name", ""),
                    "input": getattr(block, "input", {}) or {},
                }
                tool_uses.append(tu)
                assistant_blocks.append(
                    {
                        "type": "tool_use",
                        "id": tu["id"],
                        "name": tu["name"],
                        "input": tu["input"],
                    }
                )

        final_text = accumulated_text

        stop_reason = getattr(final_message, "stop_reason", "end_turn")

        if stop_reason != "tool_use" or not tool_uses:
            # Done. Persist assistant message and exit.
            for tu in tool_uses:
                persisted_tool_calls.append(
                    {
                        "id": tu["id"],
                        "type": "function",
                        "function": {"name": tu["name"], "arguments": json.dumps(tu["input"])},
                    }
                )
            break

        # Execute every tool_use, emit tool_call SSE events, build tool_result content for next turn.
        tool_result_blocks: list[dict[str, Any]] = []
        for tu in tool_uses:
            result, side = await _execute_tool(
                db,
                tenant_id=tenant_id,
                tool_name=tu["name"],
                tool_input=tu["input"],
                confirmed_draft_id=confirmed_draft_id,
            )
            if side is not None:
                yield "data: " + json.dumps(side) + "\n\n"
            yield (
                "data: "
                + json.dumps({"type": "tool_call", "name": tu["name"], "result": result})
                + "\n\n"
            )
            tool_result_blocks.append(
                {
                    "type": "tool_result",
                    "tool_use_id": tu["id"],
                    "content": json.dumps(result),
                }
            )
            persisted_tool_calls.append(
                {
                    "id": tu["id"],
                    "type": "function",
                    "function": {"name": tu["name"], "arguments": json.dumps(tu["input"])},
                }
            )

        current_messages = (
            current_messages
            + [{"role": "assistant", "content": assistant_blocks}]
            + [{"role": "user", "content": tool_result_blocks}]
        )

    asst_msg = AiMessage(
        id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        conversation_id=conv.id,
        role="assistant",
        content=final_text,
        tool_calls=persisted_tool_calls if persisted_tool_calls else None,
        model=settings.ai_model_default,
        prompt_version=SYSTEM_PROMPT_VERSION,
        input_tokens=total_input,
        output_tokens=total_output,
        cache_creation_tokens=total_cache_create,
        cache_read_tokens=total_cache_read,
        version=1,
        created_by=user_id,
        updated_by=user_id,
    )
    db.add(asst_msg)
    await db.commit()

    yield "data: " + json.dumps({"type": "done"}) + "\n\n"


async def _run_deepseek(
    db: AsyncSession,
    client: Any,
    *,
    conv: AiConversation,
    tenant_id: str,
    user_id: str,
    user_message: str,
    confirmed_draft_id: str | None,
) -> AsyncGenerator[str, None]:
    """Legacy DeepSeek path — kept until all deployments have ANTHROPIC_API_KEY."""
    history = await _load_history_deepseek(db, conv.id)
    history.append({"role": "user", "content": user_message})

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

    system_message = {"role": "system", "content": SYSTEM_PROMPT}
    tenant_ctx = await build_tenant_context(db, tenant_id)
    ctx_injection = [
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
            messages=current_messages,
            tools=ALL_TOOLS_OPENAI,
            tool_choice="auto",
            stream=True,
        )

        tool_call_accum: dict[int, dict[str, Any]] = {}
        finish_reason: str | None = None

        async for chunk in stream:
            choice = chunk.choices[0] if chunk.choices else None
            if not choice:
                continue
            finish_reason = choice.finish_reason or finish_reason
            delta = choice.delta

            if delta.content:
                accumulated_text += delta.content
                yield "data: " + json.dumps({"type": "text", "delta": delta.content}) + "\n\n"

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

            if chunk.usage:
                input_tokens += chunk.usage.prompt_tokens or 0
                output_tokens += chunk.usage.completion_tokens or 0

        if finish_reason == "tool_calls" and tool_call_accum:
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

                openai_tool_calls.append(
                    {
                        "id": tool_use_id,
                        "type": "function",
                        "function": {"name": tool_name, "arguments": json.dumps(tool_input)},
                    }
                )

                result, side = await _execute_tool(
                    db,
                    tenant_id=tenant_id,
                    tool_name=tool_name,
                    tool_input=tool_input,
                    confirmed_draft_id=confirmed_draft_id,
                )
                if side is not None:
                    yield "data: " + json.dumps(side) + "\n\n"
                yield (
                    "data: "
                    + json.dumps({"type": "tool_call", "name": tool_name, "result": result})
                    + "\n\n"
                )

                tool_results_messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_use_id,
                        "content": json.dumps(result),
                    }
                )
                persisted_tool_calls.append(
                    {
                        "id": tool_use_id,
                        "type": "function",
                        "function": {"name": tool_name, "arguments": json.dumps(tool_input)},
                    }
                )

            current_messages = (
                current_messages
                + [
                    {
                        "role": "assistant",
                        "content": accumulated_text or None,
                        "tool_calls": openai_tool_calls,
                    },
                ]
                + tool_results_messages
            )
            accumulated_text = ""
        else:
            break

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

    yield "data: " + json.dumps({"type": "done"}) + "\n\n"


async def run_chat(
    db: AsyncSession,
    *,
    tenant_id: str,
    user_id: str,
    user_message: str,
    conversation_id: str | None = None,
    confirmed_draft_id: str | None = None,
) -> AsyncGenerator[str, None]:
    """Main entry point. Yields SSE-formatted strings.

    SSE event types:
      data: {"type": "text", "delta": "..."}
      data: {"type": "tool_call", "name": "...", "result": {...}}
      data: {"type": "confirmation_required", "draft_id": "...", ...}
      data: {"type": "conversation_id", "id": "..."}
      data: {"type": "done"}
      data: {"type": "error", "message": "..."}
    """
    try:
        conv = await get_or_create_conversation(
            db, tenant_id=tenant_id, user_id=user_id, conversation_id=conversation_id
        )
        yield "data: " + json.dumps({"type": "conversation_id", "id": conv.id}) + "\n\n"

        anthropic_client = _get_anthropic_client()
        if anthropic_client is not None:
            async for chunk in _run_anthropic(
                db,
                anthropic_client,
                conv=conv,
                tenant_id=tenant_id,
                user_id=user_id,
                user_message=user_message,
                confirmed_draft_id=confirmed_draft_id,
            ):
                yield chunk
            return

        deepseek_client = _get_deepseek_client()
        if deepseek_client is not None:
            async for chunk in _run_deepseek(
                db,
                deepseek_client,
                conv=conv,
                tenant_id=tenant_id,
                user_id=user_id,
                user_message=user_message,
                confirmed_draft_id=confirmed_draft_id,
            ):
                yield chunk
            return

        # No AI provider configured.
        msg = (
            "The AI assistant is not configured. Set ANTHROPIC_API_KEY (preferred) "
            "or DEEPSEEK_API_KEY to enable it."
        )
        no_key_msg = AiMessage(
            id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            conversation_id=conv.id,
            role="assistant",
            content=msg,
            version=1,
            created_by=user_id,
            updated_by=user_id,
        )
        db.add(no_key_msg)
        await db.commit()
        yield "data: " + json.dumps({"type": "text", "delta": msg}) + "\n\n"
        yield "data: " + json.dumps({"type": "done"}) + "\n\n"

    except Exception as exc:
        await db.rollback()
        yield "data: " + json.dumps({"type": "error", "message": str(exc)}) + "\n\n"
