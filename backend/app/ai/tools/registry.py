"""AI tool registry — schemas registered here, handlers wired in Phase 3.

Tool categories (from CLAUDE.md §11):
  - Read tools: free to call, no human confirmation needed
  - Draft tools: create unposted records (also free)
  - Mutation tools: require human confirmation before execution

Phase 1 (T1.15): Read tools only. No chat endpoint yet — these schemas
are pre-registered so Phase 3 can wire them into the assistant without
changing the interface contract.
"""
from __future__ import annotations

from typing import Any

# ── Tool schema type ──────────────────────────────────────────────────────────

ToolSchema = dict[str, Any]

# ── Read tools ────────────────────────────────────────────────────────────────

GET_ACCOUNT_BALANCE: ToolSchema = {
    "name": "get_account_balance",
    "description": (
        "Return the current balance for a single GL account. "
        "Use this to answer questions like 'What is the cash balance?' or "
        "'How much do we owe in accounts payable?'"
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "account_code": {
                "type": "string",
                "description": "The account code (e.g. '1000' for Cash). "
                               "Use list_accounts to discover available codes.",
            },
            "as_of_date": {
                "type": "string",
                "format": "date",
                "description": "ISO-8601 date. Defaults to today if omitted.",
            },
        },
        "required": ["account_code"],
    },
}

LIST_JOURNAL_ENTRIES: ToolSchema = {
    "name": "list_journal_entries",
    "description": (
        "List journal entries with optional filters. Returns the most recent "
        "entries first. Use to investigate transactions or answer 'show me "
        "recent entries' questions."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "status": {
                "type": "string",
                "enum": ["draft", "posted", "void"],
                "description": "Filter by status. Omit for all.",
            },
            "period_name": {
                "type": "string",
                "description": "Filter by period name (e.g. '2025-01').",
            },
            "limit": {
                "type": "integer",
                "minimum": 1,
                "maximum": 50,
                "default": 10,
                "description": "Number of entries to return.",
            },
        },
        "required": [],
    },
}

GET_PERIOD_STATUS: ToolSchema = {
    "name": "get_period_status",
    "description": (
        "Return the status of a fiscal period (open, soft_closed, hard_closed, "
        "or audited). Use to check if a period is open before attempting to "
        "post transactions."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "period_name": {
                "type": "string",
                "description": "Period name in YYYY-MM format (e.g. '2025-03').",
            },
        },
        "required": ["period_name"],
    },
}

SEARCH_TRANSACTIONS: ToolSchema = {
    "name": "search_transactions",
    "description": (
        "Full-text search across journal entry descriptions and line memos. "
        "Returns matching entries with their amounts. Use for forensic questions "
        "like 'find any entries mentioning ACME Corp'."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search text to match against descriptions.",
                "minLength": 2,
            },
            "from_date": {
                "type": "string",
                "format": "date",
                "description": "Restrict search to entries on or after this date.",
            },
            "to_date": {
                "type": "string",
                "format": "date",
                "description": "Restrict search to entries on or before this date.",
            },
            "limit": {
                "type": "integer",
                "minimum": 1,
                "maximum": 25,
                "default": 10,
            },
        },
        "required": ["query"],
    },
}

GET_TRIAL_BALANCE: ToolSchema = {
    "name": "get_trial_balance",
    "description": (
        "Return the trial balance as of a given date. Shows debit and credit "
        "totals for each account and confirms whether the books are balanced. "
        "Use to answer questions about the overall financial position."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "as_of_date": {
                "type": "string",
                "format": "date",
                "description": "ISO-8601 date. Defaults to today if omitted.",
            },
        },
        "required": [],
    },
}

# ── Registry ──────────────────────────────────────────────────────────────────

READ_TOOLS: list[ToolSchema] = [
    GET_ACCOUNT_BALANCE,
    LIST_JOURNAL_ENTRIES,
    GET_PERIOD_STATUS,
    SEARCH_TRANSACTIONS,
    GET_TRIAL_BALANCE,
]

# ── Draft tools ───────────────────────────────────────────────────────────────

DRAFT_JOURNAL_ENTRY: ToolSchema = {
    "name": "draft_journal_entry",
    "description": (
        "Create a DRAFT journal entry proposal. The entry is NOT posted to the ledger. "
        "Returns a confirmation_required result that must be shown to the user before posting. "
        "Use this whenever you want to propose a journal entry."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "date": {"type": "string", "format": "date", "description": "Entry date (YYYY-MM-DD)."},
            "period_name": {"type": "string", "description": "Period in YYYY-MM format."},
            "description": {"type": "string", "description": "Memo describing the transaction."},
            "lines": {
                "type": "array",
                "minItems": 2,
                "description": "Journal lines. Total debits must equal total credits.",
                "items": {
                    "type": "object",
                    "required": ["account_code", "debit", "credit"],
                    "properties": {
                        "account_code": {"type": "string"},
                        "description": {"type": "string"},
                        "debit": {
                            "type": "string",
                            "description": "Decimal string e.g. '1000.00'. Use '0' for credit-side lines.",
                        },
                        "credit": {
                            "type": "string",
                            "description": "Decimal string e.g. '1000.00'. Use '0' for debit-side lines.",
                        },
                    },
                },
            },
        },
        "required": ["date", "description", "lines"],
    },
}

# ── Mutation tools ────────────────────────────────────────────────────────────

POST_JOURNAL_ENTRY: ToolSchema = {
    "name": "post_journal_entry",
    "description": (
        "Post a previously drafted journal entry to the ledger. "
        "ONLY call this after the user has explicitly confirmed they want to post. "
        "Requires the draft_id returned by draft_journal_entry."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "draft_id": {
                "type": "string",
                "description": "The draft_id from draft_journal_entry.",
            },
        },
        "required": ["draft_id"],
    },
}

DRAFT_TOOLS: list[ToolSchema] = [DRAFT_JOURNAL_ENTRY]
MUTATION_TOOLS: list[ToolSchema] = [POST_JOURNAL_ENTRY]
MUTATION_TOOL_NAMES: frozenset[str] = frozenset(t["name"] for t in MUTATION_TOOLS)

# Full tool registry
ALL_TOOLS: list[ToolSchema] = READ_TOOLS + DRAFT_TOOLS + MUTATION_TOOLS

TOOL_NAMES: frozenset[str] = frozenset(t["name"] for t in ALL_TOOLS)


def get_tool_schema(name: str) -> ToolSchema | None:
    """Return the schema for a named tool, or None if not found."""
    return next((t for t in ALL_TOOLS if t["name"] == name), None)
