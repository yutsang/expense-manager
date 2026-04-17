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
    is_control_account: bool = False
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
    is_control_account: bool
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
    force: bool = False


class PeriodTransitionWarningResponse(BaseModel):
    status: str  # always "warning"
    period_id: str
    period_name: str
    open_invoices: int
    open_invoices_total: str  # Decimal string
    open_invoices_currency: str
    open_bills: int
    open_bills_total: str  # Decimal string
    open_bills_currency: str
    message: str


class PeriodListResponse(BaseModel):
    items: list[PeriodResponse]


# ── FX Rates ─────────────────────────────────────────────────────────────────


class FxRateUpsert(BaseModel):
    from_currency: str = Field(..., min_length=3, max_length=3)
    to_currency: str = Field(..., min_length=3, max_length=3)
    rate_date: date
    rate: str = Field(..., description="Rate as decimal string")
    source: str = Field(default="manual")
    force: bool = False

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

    @field_validator(
        "debit", "credit", "fx_rate", "functional_debit", "functional_credit", mode="before"
    )
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
    force: bool = Field(default=False)


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
    idempotency_key: str | None = None
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
    credit_limit: str | None = None

    @field_validator("credit_limit")
    @classmethod
    def credit_limit_must_be_non_negative_decimal(cls, v: str | None) -> str | None:
        if v is not None:
            d = Decimal(v)
            if d < 0:
                raise ValueError("credit_limit must be non-negative")
        return v


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
    credit_limit: str | None = None

    @field_validator("credit_limit")
    @classmethod
    def credit_limit_must_be_non_negative_decimal(cls, v: str | None) -> str | None:
        if v is not None:
            d = Decimal(v)
            if d < 0:
                raise ValueError("credit_limit must be non-negative")
        return v


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
    credit_limit: str | None
    risk_rating: str | None = None
    risk_rating_rationale: str | None = None
    risk_rated_by: str | None = None
    risk_rated_at: datetime | None = None
    edd_required: bool = False
    edd_approved_by: str | None = None
    edd_approved_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @field_validator("credit_limit", mode="before")
    @classmethod
    def decimal_to_str_or_none(cls, v: Any) -> str | None:
        return str(v) if v is not None else None


class RiskRatingUpdate(BaseModel):
    """Set AMLO Cap 615 risk rating for a contact."""

    risk_rating: str = Field(..., pattern="^(low|medium|high|unacceptable)$")
    risk_rating_rationale: str = Field(..., min_length=1, max_length=2000)


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
    force: bool = Field(default=False)

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

    @field_validator(
        "quantity", "unit_price", "discount_pct", "line_amount", "tax_amount", mode="before"
    )
    @classmethod
    def decimal_to_str(cls, v: Any) -> str:
        return str(v)


class InvoiceResponse(BaseModel):
    id: str
    number: str
    status: str
    authorised_by: str | None = None
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
    credit_note_for_id: str | None = None
    notes: str | None
    last_reminder_sent_at: datetime | None
    reminder_count: int
    created_at: datetime
    updated_at: datetime
    lines: list[InvoiceLineResponse] = Field(default_factory=list)

    model_config = {"from_attributes": True}

    @field_validator(
        "fx_rate", "subtotal", "tax_total", "total", "amount_due", "functional_total", mode="before"
    )
    @classmethod
    def decimal_to_str(cls, v: Any) -> str:
        return str(v)


class InvoiceListResponse(BaseModel):
    items: list[InvoiceResponse]
    next_cursor: str | None


# ── Tenant Settings ──────────────────────────────────────────────────────────


class TenantSettingsUpdate(BaseModel):
    invoice_approval_threshold: str | None = None

    @field_validator("invoice_approval_threshold")
    @classmethod
    def threshold_must_be_non_negative_decimal(cls, v: str | None) -> str | None:
        if v is not None:
            d = Decimal(v)
            if d < 0:
                raise ValueError("invoice_approval_threshold must be non-negative")
        return v


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

    @field_validator(
        "quantity", "unit_price", "discount_pct", "line_amount", "tax_amount", mode="before"
    )
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

    @field_validator(
        "fx_rate", "subtotal", "tax_total", "total", "amount_due", "functional_total", mode="before"
    )
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
    token_type: str = "bearer"  # noqa: S105


class AuthUserResponse(BaseModel):
    id: str
    email: str
    display_name: str


class SignupResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"  # noqa: S105
    user: AuthUserResponse
    tenant_id: str
    tenant_name: str


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"  # noqa: S105
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
    def model_validate(cls, obj: Any, **kwargs: Any) -> PaymentAllocationResponse:  # type: ignore[override]
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
    idempotency_key: str | None = None
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
    next_cursor: str | None = None


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


# ── Bank Accounts ─────────────────────────────────────────────────────────────


class BankAccountCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    bank_name: str | None = Field(default=None, max_length=255)
    account_number: str | None = Field(default=None, max_length=100)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    coa_account_id: str | None = None
    is_active: bool = True


class BankAccountResponse(BaseModel):
    id: str
    name: str
    bank_name: str | None
    account_number: str | None
    currency: str
    coa_account_id: str | None
    is_active: bool
    last_reconciled_at: datetime | None
    last_reconciled_balance: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @field_validator("last_reconciled_balance", mode="before")
    @classmethod
    def decimal_to_str_or_none(cls, v: Any) -> str | None:
        return str(v) if v is not None else None


# ── Bank Transactions ─────────────────────────────────────────────────────────


class BankTransactionCreate(BaseModel):
    transaction_date: date
    description: str | None = Field(default=None, max_length=500)
    reference: str | None = Field(default=None, max_length=200)
    amount: str = Field(..., description="Positive = money in, negative = money out")
    currency: str = Field(default="USD", min_length=3, max_length=3)

    @field_validator("amount")
    @classmethod
    def amount_must_be_decimal(cls, v: str) -> str:
        try:
            Decimal(v)
        except Exception:
            raise ValueError("amount must be a valid decimal string")
        return v


class BankTransactionResponse(BaseModel):
    id: str
    bank_account_id: str
    transaction_date: Any  # date stored as Date column
    description: str | None
    reference: str | None
    amount: str
    currency: str
    is_reconciled: bool
    reconciled_at: datetime | None
    journal_line_id: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @field_validator("amount", mode="before")
    @classmethod
    def decimal_to_str(cls, v: Any) -> str:
        return str(v)

    @field_validator("transaction_date", mode="before")
    @classmethod
    def date_to_str(cls, v: Any) -> str:
        return str(v)


class MatchTransactionRequest(BaseModel):
    journal_line_id: str


class BankTransactionUpdate(BaseModel):
    transaction_date: date | None = None
    description: str | None = Field(default=None, max_length=500)
    reference: str | None = Field(default=None, max_length=200)
    amount: str | None = Field(
        default=None, description="Positive = money in, negative = money out"
    )

    @field_validator("amount")
    @classmethod
    def amount_must_be_decimal(cls, v: str | None) -> str | None:
        if v is not None:
            try:
                Decimal(v)
            except Exception:
                raise ValueError("amount must be a valid decimal string")
        return v


class UnreconcileRequest(BaseModel):
    reason: str = Field(..., min_length=1, max_length=500)


# ── Bank Reconciliations ──────────────────────────────────────────────────────


class BankReconciliationCreate(BaseModel):
    period_id: str | None = None
    statement_closing_balance: str = Field(
        ..., description="Statement closing balance as decimal string"
    )
    book_balance: str = Field(..., description="Book balance as decimal string")
    status: str = Field(default="in_progress", pattern="^(in_progress|completed)$")

    @field_validator("statement_closing_balance", "book_balance")
    @classmethod
    def must_be_decimal(cls, v: str) -> str:
        try:
            Decimal(v)
        except Exception:
            raise ValueError("must be a valid decimal string")
        return v


class BankReconciliationResponse(BaseModel):
    id: str
    bank_account_id: str
    period_id: str | None
    statement_closing_balance: str
    book_balance: str
    difference: str
    status: str
    reconciled_at: datetime | None
    reconciled_by: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @field_validator("statement_closing_balance", "book_balance", "difference", mode="before")
    @classmethod
    def decimal_to_str(cls, v: Any) -> str:
        return str(v)


# ── Expense Claims ────────────────────────────────────────────────────────────


class ExpenseClaimLineCreate(BaseModel):
    account_id: str
    tax_code_id: str | None = None
    description: str | None = Field(default=None, max_length=500)
    amount: str = Field(..., description="Line amount as decimal string")
    tax_amount: str = Field(default="0", description="Tax amount as decimal string")
    receipt_url: str | None = Field(default=None, max_length=1000)

    @field_validator("amount", "tax_amount")
    @classmethod
    def must_be_non_negative(cls, v: str) -> str:
        if Decimal(v) < 0:
            raise ValueError("must be non-negative")
        return v


class ExpenseClaimCreate(BaseModel):
    contact_id: str
    claim_date: date
    title: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    currency: str = Field(default="USD", min_length=3, max_length=3)
    lines: list[ExpenseClaimLineCreate] = Field(..., min_length=1)


class ExpenseClaimLineResponse(BaseModel):
    id: str
    account_id: str
    tax_code_id: str | None
    description: str | None
    amount: str
    tax_amount: str
    receipt_url: str | None

    model_config = {"from_attributes": True}

    @field_validator("amount", "tax_amount", mode="before")
    @classmethod
    def decimal_to_str(cls, v: Any) -> str:
        return str(v)


class ExpenseClaimResponse(BaseModel):
    id: str
    number: str
    contact_id: str
    status: str
    claim_date: Any  # date stored as Date column
    title: str
    description: str | None
    currency: str
    total_amount: str
    tax_total: str
    journal_entry_id: str | None
    approved_by: str | None
    approved_at: datetime | None
    paid_by: str | None
    paid_at: datetime | None
    created_at: datetime
    updated_at: datetime
    lines: list[ExpenseClaimLineResponse] = Field(default_factory=list)

    model_config = {"from_attributes": True}

    @field_validator("total_amount", "tax_total", mode="before")
    @classmethod
    def decimal_to_str(cls, v: Any) -> str:
        return str(v)

    @field_validator("claim_date", mode="before")
    @classmethod
    def date_to_str(cls, v: Any) -> str:
        return str(v)


class ExpenseClaimListResponse(BaseModel):
    items: list[ExpenseClaimResponse]


# ── KYC / Sanctions ───────────────────────────────────────────────────────────


class ContactKycUpdate(BaseModel):
    id_type: str | None = Field(
        default=None, pattern="^(passport|national_id|drivers_license|other)$"
    )
    id_number: str | None = Field(default=None, max_length=100)
    id_expiry_date: date | None = None
    poa_type: str | None = Field(
        default=None, pattern="^(utility_bill|bank_statement|tax_document|other)$"
    )
    poa_date: date | None = None
    sanctions_status: str | None = Field(
        default=None, pattern="^(not_checked|clear|flagged|under_review)$"
    )
    kyc_status: str | None = Field(default=None, pattern="^(pending|approved|expired|flagged)$")
    kyc_approved_by: str | None = None
    last_review_date: date | None = None
    next_review_date: date | None = None
    notes: str | None = None


class ContactKycResponse(BaseModel):
    id: str
    contact_id: str
    id_type: str | None
    id_number: str | None
    id_expiry_date: date | None
    poa_type: str | None
    poa_date: date | None
    sanctions_status: str
    sanctions_checked_at: datetime | None
    kyc_status: str
    kyc_approved_at: datetime | None
    kyc_approved_by: str | None
    last_review_date: date | None
    next_review_date: date | None
    notes: str | None
    created_at: datetime
    updated_at: datetime
    version: int

    model_config = {"from_attributes": True}


class KycListItem(BaseModel):
    contact_id: str
    contact_name: str
    contact_type: str
    kyc_id: str | None
    id_type: str | None
    id_number: str | None
    id_expiry_date: date | None
    poa_type: str | None
    poa_date: date | None
    sanctions_status: str
    sanctions_checked_at: datetime | None
    kyc_status: str
    kyc_approved_at: datetime | None
    kyc_approved_by: str | None
    last_review_date: date | None
    next_review_date: date | None
    notes: str | None
    created_at: datetime | None
    updated_at: datetime | None
    version: int | None


class KycDashboardAlerts(BaseModel):
    id_expiring_soon: int
    id_expired: int
    poa_stale: int
    pending_kyc: int
    flagged: int
    unrated_contacts: int = 0


# ── Sanctions ─────────────────────────────────────────────────────────────────


class SanctionsSnapshotResponse(BaseModel):
    id: str
    source: str
    fetched_at: datetime
    entry_count: int
    sha256_hash: str
    is_active: bool
    notes: str | None

    model_config = {"from_attributes": True}


class ContactScreeningResultResponse(BaseModel):
    id: str
    contact_id: str
    screened_at: datetime
    match_status: str
    match_score: int
    matched_name: str | None
    details: list[dict[str, Any]]

    model_config = {"from_attributes": True}


class SanctionsEntryResponse(BaseModel):
    id: str
    ref_id: str
    entity_type: str
    primary_name: str
    aliases: list[dict[str, Any]]
    countries: list[str]
    programs: list[str]
    remarks: str | None
    source: str

    model_config = {"from_attributes": True}


class SanctionsEntryListResponse(BaseModel):
    items: list[SanctionsEntryResponse]
    total: int


# ── Bank Import ───────────────────────────────────────────────────────────────


class BankImportResult(BaseModel):
    imported: int
    skipped_duplicates: int
    errors: list[str]


# ── Receipts ──────────────────────────────────────────────────────────────────


class ReceiptOcrLine(BaseModel):
    description: str | None = None
    quantity: float | None = None
    unit_price: float | None = None
    amount: float | None = None


class ReceiptResponse(BaseModel):
    id: str
    tenant_id: str
    filename: str
    content_type: str
    file_size_kb: int
    status: str
    ocr_vendor: str | None
    ocr_date: str | None
    ocr_currency: str | None
    ocr_total: str | None
    ocr_raw: dict
    linked_bill_id: str | None
    created_at: datetime

    model_config = {"from_attributes": True}

    @field_validator("ocr_total", mode="before")
    @classmethod
    def decimal_to_str_or_none(cls, v: Any) -> str | None:
        return str(v) if v is not None else None
