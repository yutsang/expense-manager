"""Unit tests for AI tool registry and schema shapes."""

from __future__ import annotations

import pytest

from app.ai.tools.registry import (
    ALL_TOOLS,
    READ_TOOLS,
    TOOL_NAMES,
    get_tool_schema,
)


class TestToolRegistry:
    def test_read_tools_registered(self) -> None:
        names = {t["name"] for t in READ_TOOLS}
        assert "get_account_balance" in names
        assert "list_journal_entries" in names
        assert "get_period_status" in names
        assert "search_transactions" in names
        assert "get_trial_balance" in names

    def test_all_tools_superset_of_read_tools(self) -> None:
        read_names = {t["name"] for t in READ_TOOLS}
        all_names = {t["name"] for t in ALL_TOOLS}
        assert read_names.issubset(all_names)

    def test_tool_names_frozenset(self) -> None:
        assert isinstance(TOOL_NAMES, frozenset)
        assert "get_account_balance" in TOOL_NAMES

    def test_get_tool_schema_found(self) -> None:
        schema = get_tool_schema("get_account_balance")
        assert schema is not None
        assert schema["name"] == "get_account_balance"

    def test_get_tool_schema_not_found(self) -> None:
        assert get_tool_schema("nonexistent_tool") is None


class TestToolSchemaShape:
    """Each tool must conform to the Anthropic tool-use schema spec."""

    @pytest.mark.parametrize("tool", READ_TOOLS)
    def test_has_name(self, tool: dict) -> None:
        assert "name" in tool
        assert isinstance(tool["name"], str)
        assert len(tool["name"]) > 0

    @pytest.mark.parametrize("tool", READ_TOOLS)
    def test_has_description(self, tool: dict) -> None:
        assert "description" in tool
        assert isinstance(tool["description"], str)
        assert len(tool["description"]) >= 10  # meaningful description

    @pytest.mark.parametrize("tool", READ_TOOLS)
    def test_has_input_schema(self, tool: dict) -> None:
        assert "input_schema" in tool
        schema = tool["input_schema"]
        assert schema["type"] == "object"
        assert "properties" in schema

    @pytest.mark.parametrize("tool", READ_TOOLS)
    def test_required_is_list(self, tool: dict) -> None:
        schema = tool["input_schema"]
        if "required" in schema:
            assert isinstance(schema["required"], list)


class TestSpecificToolSchemas:
    def test_get_account_balance_account_code_required(self) -> None:
        schema = get_tool_schema("get_account_balance")
        assert schema is not None
        assert "account_code" in schema["input_schema"]["required"]

    def test_get_account_balance_has_as_of_date(self) -> None:
        schema = get_tool_schema("get_account_balance")
        assert schema is not None
        assert "as_of_date" in schema["input_schema"]["properties"]

    def test_search_transactions_query_required(self) -> None:
        schema = get_tool_schema("search_transactions")
        assert schema is not None
        assert "query" in schema["input_schema"]["required"]

    def test_search_transactions_limit_bounded(self) -> None:
        schema = get_tool_schema("search_transactions")
        assert schema is not None
        limit_schema = schema["input_schema"]["properties"]["limit"]
        assert limit_schema["maximum"] <= 25

    def test_list_journals_limit_bounded(self) -> None:
        schema = get_tool_schema("list_journal_entries")
        assert schema is not None
        limit_schema = schema["input_schema"]["properties"]["limit"]
        assert limit_schema["maximum"] <= 50

    def test_get_period_status_period_name_required(self) -> None:
        schema = get_tool_schema("get_period_status")
        assert schema is not None
        assert "period_name" in schema["input_schema"]["required"]
