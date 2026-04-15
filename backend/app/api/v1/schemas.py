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


# ── Contacts ──────────────────────────────────────────────────────────────────

class ContactCreate(BaseModel):
    contact_type: str = Field(..., pattern="^(customer|supplier|both|employee)$")
    name: str = Field(..., min_length=1, max_length=255)
    code: str | None = Field(default=None, max_length=64)
    email: str | None = None
    phone: str | None = None
    currency: str = Field(default="USD", min_length=3, max_length=3)
    tax_number: str | None = None
    address_line1: str | None = None
    address_line2: str | None = None
    city: str | None = None
    region: str | None = None
    postal_code: str | None = None
    country: str | None = None


class ContactUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    code: str | None = None
    email: str | None = None
    phone: str | None = None
    currency: str | None = None
    tax_number: str | None = None
    address_line1: str | None = None
    address_line2: str | None = None
    city: str | None = None
    region: str | None = None
    postal_code: str | None = None
    country: str | None = None
    contact_type: str | None = Field(default=None, pattern="^(customer|supplier|both|employee)$")


class ContactResponse(BaseModel):
    id: str
    contact_type: str
    name: str
    code: str | None
    email: str | None
    phone: str | None
    currency: str
    tax_number: str | None
    address_line1: str | None
    address_line2: str | None
    city: str | None
    region: str | None
    postal_code: str | None
    country: str | None
    is_archived: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ContactListResponse(BaseModel):
    items: list[ContactResponse]
    next_cursor: str | None


# ── Items ─────────────────────────────────────────────────────────────────────

class ItemCreate(BaseModel):
    code: str = Field(..., min_length=1, max_length=64)
    name: str = Field(..., min_length=1, max_length=255)
    item_type: str = Field(..., pattern="^(product|service)$")
    description: str | None = None
    unit_of_measure: str | None = None
    sales_unit_price: str | None = None
    purchase_unit_price: str | None = None
    currency: str = Field(default="USD", min_length=3, max_length=3)
    sales_account_id: str | None = None
    cogs_account_id: str | None = None
    purchase_account_id: str | None = None
    is_tracked: bool = False

    @field_validator("sales_unit_price", "purchase_unit_price")
    @classmethod
    def price_non_negative(cls, v: str | None) -> str | None:
        if v is not None and Decimal(v) < 0:
            raise ValueError("price must be non-negative")
        return v


class ItemUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    unit_of_measure: str | None = None
    sales_unit_price: str | None = None
    purchase_unit_price: str | None = None
    currency: str | None = None
    sales_account_id: str | None = None
    cogs_account_id: str | None = None
    purchase_account_id: str | None = None
    is_tracked: bool | None = None


class ItemResponse(BaseModel):
    id: str
    code: str
    name: str
    item_type: str
    description: str | None
    unit_of_measure: str | None
    sales_unit_price: str | None
    purchase_unit_price: str | None
    currency: str
    sales_account_id: str | None
    cogs_account_id: str | None
    purchase_account_id: str | None
    is_tracked: bool
    is_archived: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @field_validator("sales_unit_price", "purchase_unit_price", mode="before")
    @classmethod
    def decimal_to_str_or_none(cls, v: Any) -> str | None:
        return str(v) if v is not None else None


class ItemListResponse(BaseModel):
    items: list[ItemResponse]
    next_cursor: str | None


# ── Tax Codes ─────────────────────────────────────────────────────────────────

class TaxCodeCreate(BaseModel):
    code: str = Field(..., min_length=1, max_length=32)
    name: str = Field(..., min_length=1, max_length=128)
    rate: str = Field(..., description="Rate as decimal 0–1, e.g. '0.1' for 10%")
    tax_type: str = Field(..., pattern="^(output|input|exempt|zero)$")
    country: str = Field(..., min_length=2, max_length=10)
    tax_collected_account_id: str | None = None
    tax_paid_account_id: str | None = None

    @field_validator("rate")
    @classmethod
    def rate_in_range(cls, v: str) -> str:
        r = Decimal(v)
        if r < 0 or r > 1:
            raise ValueError("rate must be between 0 and 1")
        return v


class TaxCodeUpdate(BaseModel):
    name: str | None = None
    rate: str | None = None
    tax_type: str | None = Field(default=None, pattern="^(output|input|exempt|zero)$")
    is_active: bool | None = None
    tax_collected_account_id: str | None = None
    tax_paid_account_id: str | None = None


class TaxCodeResponse(BaseModel):
    id: str
    code: str
    name: str
    rate: str
    tax_type: str
    country: str
    is_active: bool
    tax_collected_account_id: str | None
    tax_paid_account_id: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @field_validator("rate", mode="before")
    @classmethod
    def decimal_to_str(cls, v: Any) -> str:
        return str(v)


class TaxCodeListResponse(BaseModel):
    items: list[TaxCodeResponse]


# ── Invoices ──────────────────────────────────────────────────────────────────

class InvoiceLineCreate(BaseModel):
    account_id: str
    item_id: str | None = None
    tax_code_id: str | None = None
    description: str | None = None
    quantity: str = Field(default="1")
    unit_price: str = Field(default="0")
    discount_pct: str = Field(default="0")

    @field_validator("quantity", "unit_price", "discount_pct")
    @classmethod
    def must_be_non_negative(cls, v: str) -> str:
        if Decimal(v) < 0:
            raise ValueError("must be non-negative")
        return v


class InvoiceCreate(BaseModel):
    contact_id: str
    issue_date: date
    due_date: date | None = None
    currency: str = Field(default="USD", min_length=3, max_length=3)
    fx_rate: str = Field(default="1")
    period_name: str | None = None
    reference: str | None = None
    notes: str | None = None
    lines: list[InvoiceLineCreate] = Field(..., min_length=1)

    @field_validator("fx_rate")
    @classmethod
    def fx_positive(cls, v: str) -> str:
        if Decimal(v) <= 0:
            raise ValueError("fx_rate must be positive")
        return v


class InvoiceLineResponse(BaseModel):
    id: str
    line_no: int
    item_id: str | None
    account_id: str
    tax_code_id: str | None
    description: str | None
    quantity: str
    unit_price: str
    discount_pct: str
    line_amount: str
    tax_amount: str

    model_config = {"from_attributes": True}

    @field_validator("quantity", "unit_price", "discount_pct", "line_amount", "tax_amount", mode="before")
    @classmethod
    def decimal_to_str(cls, v: Any) -> str:
        return str(v)


class InvoiceResponse(BaseModel):
    id: str
    number: str
    status: str
    contact_id: str
    issue_date: str
    due_date: str | None
    period_name: str | None
    reference: str | None
    currency: str
    fx_rate: str
    subtotal: str
    tax_total: str
    total: str
    amount_due: str
    functional_total: str
    journal_entry_id: str | None
    notes: str | None
    created_at: datetime
    updated_at: datetime
    lines: list[InvoiceLineResponse] = Field(default_factory=list)

    model_config = {"from_attributes": True}

    @field_validator("fx_rate", "subtotal", "tax_total", "total", "amount_due", "functional_total", mode="before")
    @classmethod
    def decimal_to_str(cls, v: Any) -> str:
        return str(v)


class InvoiceListResponse(BaseModel):
    items: list[InvoiceResponse]
    next_cursor: str | None


# ── Bills ─────────────────────────────────────────────────────────────────────

class BillLineCreate(BaseModel):
    account_id: str
    item_id: str | None = None
    tax_code_id: str | None = None
    description: str | None = None
    quantity: str = Field(default="1")
    unit_price: str = Field(default="0")
    discount_pct: str = Field(default="0")

    @field_validator("quantity", "unit_price", "discount_pct")
    @classmethod
    def must_be_non_negative(cls, v: str) -> str:
        if Decimal(v) < 0:
            raise ValueError("must be non-negative")
        return v


class BillCreate(BaseModel):
    contact_id: str
    issue_date: date
    due_date: date | None = None
    currency: str = Field(default="USD", min_length=3, max_length=3)
    fx_rate: str = Field(default="1")
    period_name: str | None = None
    supplier_reference: str | None = None
    notes: str | None = None
    lines: list[BillLineCreate] = Field(..., min_length=1)


class BillLineResponse(BaseModel):
    id: str
    line_no: int
    item_id: str | None
    account_id: str
    tax_code_id: str | None
    description: str | None
    quantity: str
    unit_price: str
    discount_pct: str
    line_amount: str
    tax_amount: str

    model_config = {"from_attributes": True}

    @field_validator("quantity", "unit_price", "discount_pct", "line_amount", "tax_amount", mode="before")
    @classmethod
    def decimal_to_str(cls, v: Any) -> str:
        return str(v)


class BillResponse(BaseModel):
    id: str
    number: str
    status: str
    contact_id: str
    supplier_reference: str | None
    issue_date: str
    due_date: str | None
    period_name: str | None
    currency: str
    fx_rate: str
    subtotal: str
    tax_total: str
    total: str
    amount_due: str
    functional_total: str
    journal_entry_id: str | None
    notes: str | None
    approved_by: str | None
    approved_at: datetime | None
    created_at: datetime
    updated_at: datetime
    lines: list[BillLineResponse] = Field(default_factory=list)

    model_config = {"from_attributes": True}

    @field_validator("fx_rate", "subtotal", "tax_total", "total", "amount_due", "functional_total", mode="before")
    @classmethod
    def decimal_to_str(cls, v: Any) -> str:
        return str(v)


class BillListResponse(BaseModel):
    items: list[BillResponse]
    next_cursor: str | None


# ── Dashboard ─────────────────────────────────────────────────────────────────

class DashboardResponse(BaseModel):
    cash_balance: str
    accounts_receivable: str
    accounts_payable: str
    revenue_mtd: str
    expenses_mtd: str
    invoices_overdue: int
    bills_awaiting_approval: int
    generated_at: datetime


# ── Auth ─────────────────────────────────────────────────────────────────────

class SignupRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=254)
    password: str = Field(..., min_length=8, max_length=128)
    display_name: str = Field(..., min_length=1, max_length=255)
    tenant_name: str = Field(..., min_length=1, max_length=255)
    country: str = Field(default="US", min_length=2, max_length=10)
    currency: str = Field(default="USD", min_length=3, max_length=3)


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class AuthUserResponse(BaseModel):
    id: str
    email: str
    display_name: str


class SignupResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: AuthUserResponse
    tenant_id: str
    tenant_name: str


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: AuthUserResponse
    tenant_ids: list[str]


# ── Payments ─────────────────────────────────────────────────────────────────

class PaymentCreate(BaseModel):
    payment_type: str = Field(..., pattern="^(received|made)$")
    contact_id: str
    amount: str  # Decimal string
    currency: str = Field(default="USD", min_length=3, max_length=3)
    fx_rate: str = Field(default="1")
    payment_date: str  # ISO date
    reference: str | None = None
    bank_account_ref: str | None = None


class PaymentAllocationCreate(BaseModel):
    invoice_id: str | None = None
    bill_id: str | None = None
    amount_applied: str  # Decimal string


class PaymentAllocationResponse(BaseModel):
    id: str
    payment_id: str
    invoice_id: str | None
    bill_id: str | None
    amount_applied: str
    created_at: datetime

    model_config = {"from_attributes": True, "populate_by_name": True}

    @classmethod
    def model_validate(cls, obj: Any, **kwargs: Any) -> "PaymentAllocationResponse":  # type: ignore[override]
        # ORM column is `amount`; expose as `amount_applied`
        if hasattr(obj, "__dict__"):
            d = {**obj.__dict__}
            if "amount" in d and "amount_applied" not in d:
                d["amount_applied"] = str(d["amount"])
            return super().model_validate(d, **kwargs)
        return super().model_validate(obj, **kwargs)


class PaymentResponse(BaseModel):
    id: str
    number: str
    payment_type: str
    contact_id: str
    amount: str
    currency: str
    fx_rate: str
    payment_date: str
    reference: str | None
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @field_validator("amount", "fx_rate", mode="before")
    @classmethod
    def decimal_to_str(cls, v: Any) -> str:
        return str(v)


class PaymentListResponse(BaseModel):
    items: list[PaymentResponse]
    total: int


class PaymentVoidRequest(BaseModel):
    reason: str = Field(default="Voided by user", min_length=1, max_length=500)


# ── P&L Report ────────────────────────────────────────────────────────────────

class PLLineResponse(BaseModel):
    account_id: str
    code: str
    name: str
    subtype: str
    balance: str


class PLResponse(BaseModel):
    from_date: date
    to_date: date
    total_revenue: str
    total_expenses: str
    net_profit: str
    is_profitable: bool
    revenue_lines: list[PLLineResponse]
    expense_lines: list[PLLineResponse]
    generated_at: datetime


# ── Balance Sheet ─────────────────────────────────────────────────────────────

class BalanceSheetLineResponse(BaseModel):
    account_id: str
    code: str
    name: str
    subtype: str
    balance: str  # debit - credit for assets, credit - debit for liabilities/equity


class BalanceSheetSectionResponse(BaseModel):
    total: str
    lines: list[BalanceSheetLineResponse]


class BalanceSheetResponse(BaseModel):
    as_of: date
    assets: BalanceSheetSectionResponse
    liabilities: BalanceSheetSectionResponse
    equity: BalanceSheetSectionResponse
    total_liabilities_and_equity: str
    is_balanced: bool  # abs(assets.total - total_liabilities_and_equity) < 0.01
    generated_at: datetime


# ── AR / AP Aging ─────────────────────────────────────────────────────────────

class AgingRowResponse(BaseModel):
    contact_id: str
    contact_name: str
    invoice_number: str
    issue_date: str
    due_date: str | None
    total: str
    amount_due: str
    days_overdue: int  # max(0, (as_of - due_date).days) if due_date else 0
    bucket: str  # "current" | "1-30" | "31-60" | "61-90" | "90+"


class AgingResponse(BaseModel):
    as_of: date
    current_total: str
    bucket_1_30: str
    bucket_31_60: str
    bucket_61_90: str
    bucket_90_plus: str
    grand_total: str
    rows: list[AgingRowResponse]
    generated_at: datetime


# ── Cash Flow ─────────────────────────────────────────────────────────────────

class CashFlowLineResponse(BaseModel):
    label: str
    amount: str
    is_subtotal: bool = False


class CashFlowResponse(BaseModel):
    from_date: date
    to_date: date
    operating_activities: list[CashFlowLineResponse]
    investing_activities: list[CashFlowLineResponse]
    financing_activities: list[CashFlowLineResponse]
    net_operating: str
    net_investing: str
    net_financing: str
    net_change: str
    opening_cash: str
    closing_cash: str
    generated_at: datetime
