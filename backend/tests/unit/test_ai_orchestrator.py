"""Unit tests for the AI orchestrator after the Anthropic migration.

Covers:
  - Client selection (Anthropic when key present, DeepSeek when only DeepSeek set, none otherwise)
  - System prompt is composed as a list of cache-marked text blocks
  - Tool execution dispatch routes to the correct handler category
  - Draft handler errors on unbalanced journal entries
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestClientSelection:
    def test_anthropic_client_returned_when_key_set(self) -> None:
        from app.ai import orchestrator

        with patch.object(orchestrator.settings, "anthropic_api_key", "sk-ant-test"):
            client = orchestrator._get_anthropic_client()
            assert client is not None
            # AsyncAnthropic is lazy-imported; just verify it's not None.

    def test_anthropic_client_none_when_key_empty(self) -> None:
        from app.ai import orchestrator

        with patch.object(orchestrator.settings, "anthropic_api_key", ""):
            assert orchestrator._get_anthropic_client() is None

    def test_deepseek_client_none_when_key_empty(self) -> None:
        from app.ai import orchestrator

        with patch.object(orchestrator.settings, "deepseek_api_key", ""):
            assert orchestrator._get_deepseek_client() is None


class TestSystemPromptStructure:
    """The Anthropic path must send the system prompt as cache-marked blocks (CLAUDE.md §11.2)."""

    def test_orchestrator_constructs_cached_system_blocks(self) -> None:
        # Import the module and inspect the source of _run_anthropic to ensure it
        # composes the system_blocks with cache_control. This is a structural
        # guard; a full streaming test requires mocking the Anthropic stream API.
        import inspect

        from app.ai import orchestrator

        src = inspect.getsource(orchestrator._run_anthropic)
        assert "cache_control" in src, "Prompt caching markers missing from _run_anthropic"
        assert "ephemeral" in src
        assert "tenant_context" in src

    def test_orchestrator_passes_tools_to_anthropic(self) -> None:
        import inspect

        from app.ai import orchestrator

        src = inspect.getsource(orchestrator._run_anthropic)
        assert "tools=ALL_TOOLS" in src, "Tool registry must be passed to Anthropic call"

    def test_orchestrator_records_cache_metrics(self) -> None:
        import inspect

        from app.ai import orchestrator

        src = inspect.getsource(orchestrator._run_anthropic)
        assert "cache_creation_input_tokens" in src
        assert "cache_read_input_tokens" in src
        assert "cache_creation_tokens=" in src, "Must persist cache metrics on AiMessage"


class TestToolDispatch:
    @pytest.mark.asyncio
    async def test_mutation_tool_unconfirmed_returns_confirmation_required(self) -> None:
        from app.ai.orchestrator import _execute_tool

        db = MagicMock()
        result, side = await _execute_tool(
            db,
            tenant_id="t1",
            tool_name="post_journal_entry",
            tool_input={"draft_id": "abc"},
            confirmed_draft_id=None,
        )
        assert result.get("confirmation_required") is True
        assert side is not None
        assert side["type"] == "confirmation_required"
        assert side["draft_id"] == "abc"

    @pytest.mark.asyncio
    async def test_read_tool_dispatches_to_read_handlers(self) -> None:
        from app.ai import orchestrator

        fake_result = {"balance": "100.00"}
        with patch.object(
            orchestrator, "read_dispatch", AsyncMock(return_value=fake_result)
        ) as mock:
            result, side = await orchestrator._execute_tool(
                MagicMock(),
                tenant_id="t1",
                tool_name="get_account_balance",
                tool_input={"account_code": "1000"},
                confirmed_draft_id=None,
            )
        mock.assert_awaited_once()
        assert result == fake_result
        assert side is None


class TestDraftPersistence:
    """Drafts are persisted to the ai_drafts table, not an in-memory dict."""

    @pytest.mark.asyncio
    async def test_draft_journal_entry_validates_balance(self) -> None:
        from app.ai.tools.draft_handlers import handle_draft_journal_entry

        db = MagicMock()
        db.execute = AsyncMock()
        db.add = MagicMock()
        db.flush = AsyncMock()

        result = await handle_draft_journal_entry(
            db,
            "tenant-1",
            {
                "date": "2026-01-01",
                "description": "test",
                "lines": [
                    {"account_code": "1000", "debit": "100", "credit": "0"},
                    {"account_code": "2000", "debit": "0", "credit": "50"},  # unbalanced
                ],
            },
        )
        assert "error" in result
        assert "not balanced" in result["error"]
        # No draft should have been stored.
        db.add.assert_not_called()

    def test_draft_ttl_is_24_hours(self) -> None:
        from datetime import timedelta

        from app.ai.tools.draft_handlers import DRAFT_TTL

        assert timedelta(hours=24) == DRAFT_TTL

    def test_draft_handlers_do_not_use_in_memory_dict(self) -> None:
        """Sanity check: in-memory store removed after persistence migration."""
        from app.ai.tools import draft_handlers

        assert not hasattr(draft_handlers, "_drafts"), (
            "In-memory _drafts dict must be removed; drafts are persisted in ai_drafts"
        )

    @pytest.mark.asyncio
    async def test_post_journal_entry_rejects_missing_draft(self) -> None:
        from app.ai.tools.draft_handlers import handle_post_journal_entry

        db = MagicMock()
        # No draft found
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=None)
        db.execute = AsyncMock(return_value=mock_result)

        result = await handle_post_journal_entry(
            db,
            "tenant-1",
            {"draft_id": "nonexistent"},
            confirmed=True,
        )
        assert "error" in result
        assert "not found" in result["error"].lower() or "expired" in result["error"].lower()


class TestFallbackToDeepSeek:
    """If Anthropic isn't configured but DeepSeek is, the legacy path must run."""

    def test_run_chat_entrypoint_checks_anthropic_first(self) -> None:
        import inspect

        from app.ai import orchestrator

        src = inspect.getsource(orchestrator.run_chat)
        # Anthropic check must appear before DeepSeek check in the entrypoint.
        anthropic_idx = src.find("_get_anthropic_client")
        deepseek_idx = src.find("_get_deepseek_client")
        assert anthropic_idx > 0
        assert deepseek_idx > 0
        assert anthropic_idx < deepseek_idx, (
            "Anthropic path must be preferred over DeepSeek fallback"
        )


class TestDraftBalanceMath:
    """Pure-ish test of balance detection using Decimal arithmetic."""

    @pytest.mark.asyncio
    async def test_balanced_multi_line_entry_is_accepted(self) -> None:
        """Zero net debits-minus-credits passes validation."""
        from app.ai.tools.draft_handlers import handle_draft_journal_entry

        db = MagicMock()
        db.execute = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=MagicMock(name="Cash"))
        db.execute = AsyncMock(return_value=mock_result)
        db.add = MagicMock()
        db.flush = AsyncMock()

        result = await handle_draft_journal_entry(
            db,
            "tenant-1",
            {
                "date": "2026-01-01",
                "description": "balanced entry",
                "lines": [
                    {"account_code": "1000", "debit": "150.00", "credit": "0"},
                    {"account_code": "2000", "debit": "0", "credit": "100.00"},
                    {"account_code": "3000", "debit": "0", "credit": "50.00"},
                ],
            },
        )
        # Balanced entries should be persisted and return confirmation_required
        assert result.get("confirmation_required") is True
        assert "draft_id" in result
        assert Decimal(result["proposed_entry"]["total_debit"]) == Decimal("150.00")
