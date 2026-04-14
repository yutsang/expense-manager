"""Pydantic request/response schemas for v1 API.

Rules:
- Money amounts are always strings in JSON (never float).
- All IDs are strings (UUID format).
- Dates are ISO-8601 strings.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field, field_validator


# ── Shared ────────────────────────────────────────────────────────────────────

class ProblemDetail(BaseModel):
    """RFC 7807 Problem Detail."""
    type: str = "about:blank"
    title: str
    status: int
    detail: str | None = None
    instance: str | None = None


class ApiMoney(BaseModel):
    """Money representation: amount as string, never float."""
    amount: str
    currency: str

    @field_validator("amount")
    @classmethod
    def amount_must_be_numeric(cls, v: str) -> str:
        try:
            Decimal(v)
        except Exception:
            raise ValueError("amount must be a valid decimal string")
        return v


# ── Accounts ─────────────────────────────────────────────────────────────────

class AccountCreate(BaseModel):
    code: str = Field(..., min_length=1, max_length=20)
    name: str = Field(..., min_length=1, max_length=200)
    type: str = Field(..., pattern="^(asset|liability|equity|revenue|expense)$")
    subtype: str = Field(default="other", max_length=50)
    normal_balance: str = Field(..., pattern="^(debit|credit)$")
    parent_id: str | None = None
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    description: str | None = None


class AccountUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None


class AccountResponse(BaseModel):
    id: str
    code: str
    name: str
    type: str
    subtype: str
    normal_balance: str
    parent_id: str | None
    is_active: bool
    is_system: bool
    currency: str | None
    description: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AccountListResponse(BaseModel):
    items: list[AccountResponse]
    total: int


# ── Periods ──────────────────────────────────────────────────────────────────

class PeriodResponse(BaseModel):
    id: str
    name: str
    start_date: datetime
    end_date: datetime
    status: str
    closed_at: datetime | None
    closed_by: str | None
    closed_reason: str | None
    reopened_at: datetime | None

    model_config = {"from_attributes": True}


class PeriodTransitionRequest(BaseModel):
    target_status: str = Field(..., pattern="^(open|soft_closed|hard_closed|audited)$")
    reason: str | None = None


class PeriodListResponse(BaseModel):
    items: list[PeriodResponse]


# ── FX Rates ─────────────────────────────────────────────────────────────────

class FxRateUpsert(BaseModel):
    from_currency: str = Field(..., min_length=3, max_length=3)
    to_currency: str = Field(..., min_length=3, max_length=3)
    rate_date: date
    rate: str = Field(..., description="Rate as decimal string")
    source: str = Field(default="manual")

    @field_validator("rate")
    @classmethod
    def rate_positive(cls, v: str) -> str:
        if Decimal(v) <= 0:
            raise ValueError("rate must be positive")
        return v


class FxRateResponse(BaseModel):
    id: str
    from_currency: str
    to_currency: str
    rate_date: datetime
    rate: str
    source: str
    created_at: datetime

    model_config = {"from_attributes": True}

    @field_validator("rate", mode="before")
    @classmethod
    def decimal_to_str(cls, v: Any) -> str:
        return str(v)


# ── Journal Lines ─────────────────────────────────────────────────────────────

class JournalLineCreate(BaseModel):
    account_id: str
    debit: str = Field(default="0", description="Debit amount as decimal string")
    credit: str = Field(default="0", description="Credit amount as decimal string")
    currency: str = Field(default="USD", min_length=3, max_length=3)
    fx_rate: str = Field(default="1", description="FX rate to functional currency")
    description: str | None = None
    contact_id: str | None = None

    @field_validator("debit", "credit", "fx_rate")
    @classmethod
    def must_be_non_negative_decimal(cls, v: str) -> str:
        if Decimal(v) < 0:
            raise ValueError("must be non-negative")
        return v


class JournalLineResponse(BaseModel):
    id: str
    line_no: int
    account_id: str
    contact_id: str | None
    description: str | None
    debit: str
    credit: str
    currency: str
    fx_rate: str
    functional_debit: str
    functional_credit: str

    model_config = {"from_attributes": True}

    @field_validator("debit", "credit", "fx_rate", "functional_debit", "functional_credit", mode="before")
    @classmethod
    def decimal_to_str(cls, v: Any) -> str:
        return str(v)


# ── Journal Entries ───────────────────────────────────────────────────────────

class JournalCreate(BaseModel):
    date: date
    period_id: str
    description: str = Field(..., min_length=1, max_length=500)
    lines: list[JournalLineCreate] = Field(..., min_length=2)
    source_type: str = Field(default="manual")
    source_id: str | None = None


class JournalVoidRequest(BaseModel):
    reason: str = Field(default="", max_length=500)


class JournalResponse(BaseModel):
    id: str
    number: str
    date: datetime
    period_id: str
    description: str
    status: str
    source_type: str
    source_id: str | None
    total_debit: str
    total_credit: str
    created_at: datetime
    updated_at: datetime
    posted_at: datetime | None
    lines: list[JournalLineResponse] = Field(default_factory=list)

    model_config = {"from_attributes": True}

    @field_validator("total_debit", "total_credit", mode="before")
    @classmethod
    def decimal_to_str(cls, v: Any) -> str:
        return str(v)


class JournalListResponse(BaseModel):
    items: list[JournalResponse]
    next_cursor: str | None


# ── Reports ───────────────────────────────────────────────────────────────────

class TrialBalanceRowResponse(BaseModel):
    account_id: str
    code: str
    name: str
    type: str
    normal_balance: str
    total_debit: str
    total_credit: str
    balance: str


class TrialBalanceResponse(BaseModel):
    as_of: date
    tenant_id: str
    total_debit: str
    total_credit: str
    is_balanced: bool
    generated_at: datetime
    rows: list[TrialBalanceRowResponse]


class GLLineResponse(BaseModel):
    date: date
    journal_number: str
    journal_id: str
    description: str
    debit: str
    credit: str
    running_balance: str


class GLReportResponse(BaseModel):
    account_id: str
    account_code: str
    account_name: str
    normal_balance: str
    from_date: date
    to_date: date
    opening_balance: str
    closing_balance: str
    lines: list[GLLineResponse]
