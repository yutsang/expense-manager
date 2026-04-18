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

from pydantic import BaseModel, Field, field_validator, model_validator

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


class PeriodChecklistItemResponse(BaseModel):
    task_key: str
    label: str
    checked_by: str | None
    checked_at: datetime | None


class ChecklistSignoffRequest(BaseModel):
    task_key: str = Field(..., min_length=1, max_length=64)


class PeriodChecklistResponse(BaseModel):
    period_id: str
    items: list[PeriodChecklistItemResponse]
    completed: int
    total: int


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
    submitted_by: str | None = None
    submitted_at: datetime | None = None
    approved_by: str | None = None
    approved_at: datetime | None = None
    posted_at: datetime | None = None
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

    @model_validator(mode="after")
    def due_date_not_before_issue_date(self) -> InvoiceCreate:
        if self.due_date is not None and self.due_date < self.issue_date:
            raise ValueError("Due date must be on or after issue date")
        return self


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


class SendInvoiceRequest(BaseModel):
    """Request body for sending an invoice via email."""

    to: str = Field(..., min_length=3, max_length=254)
    subject: str | None = None
    message: str | None = None


class InvoiceResponse(BaseModel):
    id: str
    number: str
    status: str
    authorised_by: str | None = None
    contact_id: str
    issue_date: date | str
    due_date: date | str | None
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
    sent_at: datetime | None
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
    org_name: str | None = None
    country: str | None = None
    functional_currency: str | None = None
    fiscal_year_start_month: int | None = None
    tax_rounding_policy: str | None = None
    notification_prefs: dict[str, bool] | None = None

    @field_validator("invoice_approval_threshold")
    @classmethod
    def threshold_must_be_non_negative_decimal(cls, v: str | None) -> str | None:
        if v is not None:
            d = Decimal(v)
            if d < 0:
                raise ValueError("invoice_approval_threshold must be non-negative")
        return v

    @field_validator("fiscal_year_start_month")
    @classmethod
    def month_must_be_valid(cls, v: int | None) -> int | None:
        if v is not None and (v < 1 or v > 12):
            raise ValueError("fiscal_year_start_month must be between 1 and 12")
        return v

    @field_validator("tax_rounding_policy")
    @classmethod
    def policy_must_be_valid(cls, v: str | None) -> str | None:
        if v is not None and v not in ("per_line", "per_invoice"):
            raise ValueError("tax_rounding_policy must be 'per_line' or 'per_invoice'")
        return v


class TenantSettingsResponse(BaseModel):
    org_name: str
    country: str
    functional_currency: str
    fiscal_year_start_month: int
    tax_rounding_policy: str
    invoice_approval_threshold: str | None = None
    notification_prefs: dict[str, bool]

    model_config = {"from_attributes": True}


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

    @model_validator(mode="after")
    def due_date_not_before_issue_date(self) -> BillCreate:
        if self.due_date is not None and self.due_date < self.issue_date:
            raise ValueError("Due date must be on or after issue date")
        return self


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
    issue_date: date | str
    due_date: date | str | None
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
    payment_date: date | str  # ISO date
    reference: str | None = None
    bank_account_ref: str | None = None

    @field_validator("amount")
    @classmethod
    def amount_must_be_positive(cls, v: str) -> str:
        if Decimal(v) <= 0:
            raise ValueError("Amount must be positive")
        return v


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
    payment_date: date | str
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
    doc_id: str  # invoice or bill ID for drill-down linking
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
    missing_ubos: int = 0


# ── UBO (Ultimate Beneficial Owner / Significant Controller — Cap 622) ───────


class ContactUBOCreate(BaseModel):
    controller_name: str = Field(..., min_length=1, max_length=255)
    id_type: str | None = Field(
        default=None, pattern="^(passport|national_id|drivers_license|other)$"
    )
    id_number: str | None = Field(default=None, max_length=100)
    nationality: str | None = Field(default=None, max_length=10)
    address: str | None = None
    ownership_pct: str = Field(..., description="Ownership percentage as decimal string (0-100)")
    control_type: str = Field(..., pattern="^(shareholding|voting_rights|board_appointment|other)$")
    is_significant_controller: bool = False
    effective_date: date
    ceased_date: date | None = None

    @field_validator("ownership_pct")
    @classmethod
    def ownership_pct_in_range(cls, v: str) -> str:
        d = Decimal(v)
        if d < 0 or d > 100:
            raise ValueError("ownership_pct must be between 0 and 100")
        return v


class ContactUBOUpdate(BaseModel):
    controller_name: str | None = Field(default=None, min_length=1, max_length=255)
    id_type: str | None = Field(
        default=None, pattern="^(passport|national_id|drivers_license|other)$"
    )
    id_number: str | None = None
    nationality: str | None = None
    address: str | None = None
    ownership_pct: str | None = None
    control_type: str | None = Field(
        default=None, pattern="^(shareholding|voting_rights|board_appointment|other)$"
    )
    is_significant_controller: bool | None = None
    effective_date: date | None = None
    ceased_date: date | None = None

    @field_validator("ownership_pct")
    @classmethod
    def ownership_pct_in_range(cls, v: str | None) -> str | None:
        if v is not None:
            d = Decimal(v)
            if d < 0 or d > 100:
                raise ValueError("ownership_pct must be between 0 and 100")
        return v


class ContactUBOResponse(BaseModel):
    id: str
    contact_id: str
    controller_name: str
    id_type: str | None
    id_number: str | None
    nationality: str | None
    address: str | None
    ownership_pct: str
    control_type: str
    is_significant_controller: bool
    effective_date: date
    ceased_date: date | None
    created_at: datetime
    updated_at: datetime
    version: int

    model_config = {"from_attributes": True}

    @field_validator("ownership_pct", mode="before")
    @classmethod
    def decimal_to_str(cls, v: Any) -> str:
        return str(v)


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


# ── Bulk Actions ─────────────────────────────────────────────────────────────


class BulkActionRequest(BaseModel):
    """Request body for bulk approve / void operations."""

    ids: list[str] = Field(..., min_length=1)


class BulkActionFailure(BaseModel):
    """One failed item in a bulk operation."""

    id: str
    error: str


class BulkActionResponse(BaseModel):
    """Response for bulk operations: lists of succeeded IDs and failed items."""

    succeeded: list[str]
    failed: list[BulkActionFailure]


# ── Onboarding (Issue #34) ──────────────────────────────────────────────────


class OnboardingSetup(BaseModel):
    """Request body for tenant onboarding wizard."""

    company_name: str = Field(..., min_length=1, max_length=255)
    legal_name: str = Field(..., min_length=1, max_length=255)
    country: str = Field(default="US", min_length=2, max_length=10)
    functional_currency: str = Field(default="USD", min_length=3, max_length=3)
    fiscal_year_start_month: int = Field(default=1, ge=1, le=12)
    coa_template: str = Field(
        ..., pattern="^(general|professional_services|retail)$"
    )
    bank_account_name: str = Field(..., min_length=1, max_length=255)
    bank_name: str | None = Field(default=None, max_length=255)
    bank_account_number: str | None = Field(default=None, max_length=100)
    bank_currency: str = Field(default="USD", min_length=3, max_length=3)
    first_contact_name: str | None = Field(default=None, max_length=255)
    first_contact_email: str | None = Field(default=None, max_length=254)
    first_contact_type: str | None = Field(
        default=None, pattern="^(customer|supplier|both)$"
    )


class OnboardingResponse(BaseModel):
    """Response from onboarding setup."""

    tenant_id: str
    setup_completed_at: str
    accounts_created: int
    periods_created: int
    bank_account_id: str | None
    first_contact_id: str | None


# ── Invoice Portal (Issue #36) ──────────────────────────────────────────────


class ShareLinkResponse(BaseModel):
    """Response from generating a share link for an invoice."""

    share_token: str
    public_url: str
    expires_at: str


class PublicInvoiceLineResponse(BaseModel):
    """Line item in public invoice view."""

    description: str | None
    quantity: str
    unit_price: str
    line_amount: str
    tax_amount: str


class PublicInvoiceResponse(BaseModel):
    """Public-facing invoice view (no internal IDs exposed)."""

    invoice_number: str
    status: str
    contact_name: str
    issue_date: str
    due_date: str | None
    currency: str
    subtotal: str
    tax_total: str
    total: str
    notes: str | None
    lines: list[PublicInvoiceLineResponse] = Field(default_factory=list)
    company_name: str
    acknowledged_at: str | None = None


class InvoiceAcknowledgeRequest(BaseModel):
    """Request body for acknowledging an invoice."""

    customer_name: str | None = Field(default=None, max_length=255)


class InvoiceAcknowledgeResponse(BaseModel):
    """Response from acknowledging an invoice."""

    acknowledged_at: str
    acknowledged_by_name: str | None


# ── Global Search (Issue #39) ───────────────────────────────────────────────


class SearchResultItem(BaseModel):
    """A single search result."""

    entity_type: str
    entity_id: str
    title: str
    subtitle: str | None = None
    url: str | None = None


class SearchResponse(BaseModel):
    """Response from global search."""

    query: str
    items: list[SearchResultItem]
    total: int


# ── Accruals / Prepayments (Issue #42) ──────────────────────────────────────


class AccrualCreate(BaseModel):
    """Request body for creating an accrual or prepayment."""

    accrual_type: str = Field(..., pattern="^(accrual|prepayment)$")
    description: str = Field(..., min_length=1, max_length=500)
    amount: str = Field(..., description="Amount as decimal string")
    currency: str = Field(default="USD", min_length=3, max_length=3)
    debit_account_id: str
    credit_account_id: str
    period_id: str

    @field_validator("amount")
    @classmethod
    def amount_must_be_positive(cls, v: str) -> str:
        d = Decimal(v)
        if d <= 0:
            raise ValueError("amount must be positive")
        return v

    @model_validator(mode="after")
    def accounts_must_differ(self) -> AccrualCreate:
        if self.debit_account_id == self.credit_account_id:
            raise ValueError("debit and credit accounts must differ")
        return self


class AccrualResponse(BaseModel):
    """Response for an accrual/prepayment record."""

    id: str
    accrual_type: str
    description: str
    amount: str
    currency: str
    debit_account_id: str
    credit_account_id: str
    period_id: str
    journal_entry_id: str | None
    reversal_journal_entry_id: str | None
    status: str
    created_at: Any
    updated_at: Any

    model_config = {"from_attributes": True}

    @field_validator("amount", mode="before")
    @classmethod
    def decimal_to_str(cls, v: Any) -> str:
        return str(v)


class AccrualListResponse(BaseModel):
    """List of accruals."""

    items: list[AccrualResponse]


# ── Bank Feed Connections ────────────────────────────────────────────────────


class BankFeedConnectRequest(BaseModel):
    provider: str = Field(default="plaid", max_length=50)
    access_token: str | None = Field(default=None, description="Encrypted provider token")
    item_id: str | None = Field(default=None, max_length=100)
    institution_id: str | None = Field(default=None, max_length=100)
    institution_name: str | None = Field(default=None, max_length=200)


class BankFeedStatusResponse(BaseModel):
    id: str
    bank_account_id: str
    provider: str
    institution_id: str | None
    institution_name: str | None
    status: str
    last_sync_at: datetime | None
    last_error: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class BankFeedSyncResponse(BaseModel):
    connection_id: str
    status: str
    transactions_synced: int
    last_sync_at: datetime | None


# ── Budgets (Issue #70) ─────────────────────────────────────────────────────


class BudgetCreate(BaseModel):
    fiscal_year: int
    name: str = Field(..., min_length=1, max_length=100)
    status: str = Field(default="draft", pattern="^(draft|active|closed)$")


class BudgetUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    status: str | None = Field(default=None, pattern="^(draft|active|closed)$")


class BudgetResponse(BaseModel):
    id: str
    fiscal_year: int
    name: str
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class BudgetListResponse(BaseModel):
    items: list[BudgetResponse]
    next_cursor: str | None


class BudgetLineCreate(BaseModel):
    account_id: str
    month_1: str = Field(default="0")
    month_2: str = Field(default="0")
    month_3: str = Field(default="0")
    month_4: str = Field(default="0")
    month_5: str = Field(default="0")
    month_6: str = Field(default="0")
    month_7: str = Field(default="0")
    month_8: str = Field(default="0")
    month_9: str = Field(default="0")
    month_10: str = Field(default="0")
    month_11: str = Field(default="0")
    month_12: str = Field(default="0")

    @field_validator(
        "month_1", "month_2", "month_3", "month_4", "month_5", "month_6",
        "month_7", "month_8", "month_9", "month_10", "month_11", "month_12",
    )
    @classmethod
    def must_be_valid_decimal(cls, v: str) -> str:
        Decimal(v)  # raises if invalid
        return v


class BudgetLineResponse(BaseModel):
    id: str
    budget_id: str
    account_id: str
    month_1: str
    month_2: str
    month_3: str
    month_4: str
    month_5: str
    month_6: str
    month_7: str
    month_8: str
    month_9: str
    month_10: str
    month_11: str
    month_12: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @field_validator(
        "month_1", "month_2", "month_3", "month_4", "month_5", "month_6",
        "month_7", "month_8", "month_9", "month_10", "month_11", "month_12",
        mode="before",
    )
    @classmethod
    def decimal_to_str(cls, v: Any) -> str:
        return str(v)


class BudgetLineListResponse(BaseModel):
    items: list[BudgetLineResponse]


class BudgetVsActualRow(BaseModel):
    account_id: str
    account_name: str
    budget_amount: str
    actual_amount: str
    variance: str
    variance_pct: str


class BudgetVsActualResponse(BaseModel):
    budget_id: str
    month: int
    rows: list[BudgetVsActualRow]


# ── Invoice Templates (Issue #66) ───────────────────────────────────────────


class InvoiceTemplateCreate(BaseModel):
    contact_id: str
    name: str = Field(..., min_length=1, max_length=200)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    lines_json: list[dict] = Field(default_factory=list)
    recurrence_frequency: str | None = Field(
        default=None, pattern="^(weekly|monthly|quarterly|annually)$"
    )
    next_generation_date: date | None = None
    end_date: date | None = None


class InvoiceTemplateUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    contact_id: str | None = None
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    lines_json: list[dict] | None = None
    recurrence_frequency: str | None = Field(
        default=None, pattern="^(weekly|monthly|quarterly|annually)$"
    )
    next_generation_date: date | None = None
    end_date: date | None = None
    is_active: bool | None = None


class InvoiceTemplateResponse(BaseModel):
    id: str
    contact_id: str
    name: str
    currency: str
    lines_json: list[dict]
    recurrence_frequency: str | None
    next_generation_date: date | None
    end_date: date | None
    is_active: bool
    last_generated_invoice_id: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class InvoiceTemplateListResponse(BaseModel):
    items: list[InvoiceTemplateResponse]
    next_cursor: str | None


class SaveAsTemplateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    recurrence_frequency: str | None = Field(
        default=None, pattern="^(weekly|monthly|quarterly|annually)$"
    )
    next_generation_date: date | None = None
    end_date: date | None = None


# ── Approval Rules (Issue #61) ─────────────────────────────────────────────


class ApprovalRuleCreate(BaseModel):
    """Request body for creating an approval rule."""

    entity_type: str = Field(
        ..., pattern="^(invoice|bill|journal|expense_claim)$"
    )
    condition_field: str = Field(..., pattern="^(total|amount)$")
    condition_operator: str = Field(..., pattern="^(gte|lte|gt|lt|eq)$")
    condition_value: str = Field(..., description="Threshold value as decimal string")
    required_role: str = Field(..., min_length=1, max_length=50)
    approval_order: int = Field(default=1, ge=1)
    description: str | None = None

    @field_validator("condition_value")
    @classmethod
    def condition_value_must_be_non_negative_decimal(cls, v: str) -> str:
        d = Decimal(v)
        if d < 0:
            raise ValueError("condition_value must be non-negative")
        return v


class ApprovalRuleUpdate(BaseModel):
    """Request body for updating an approval rule."""

    entity_type: str | None = Field(
        default=None, pattern="^(invoice|bill|journal|expense_claim)$"
    )
    condition_field: str | None = Field(default=None, pattern="^(total|amount)$")
    condition_operator: str | None = Field(
        default=None, pattern="^(gte|lte|gt|lt|eq)$"
    )
    condition_value: str | None = None
    required_role: str | None = Field(default=None, min_length=1, max_length=50)
    approval_order: int | None = Field(default=None, ge=1)
    description: str | None = None
    is_active: bool | None = None

    @field_validator("condition_value")
    @classmethod
    def condition_value_must_be_non_negative_decimal(cls, v: str | None) -> str | None:
        if v is not None:
            d = Decimal(v)
            if d < 0:
                raise ValueError("condition_value must be non-negative")
        return v


class ApprovalRuleResponse(BaseModel):
    """Response for an approval rule."""

    id: str
    tenant_id: str
    entity_type: str
    condition_field: str
    condition_operator: str
    condition_value: str
    required_role: str
    approval_order: int
    is_active: bool
    description: str | None
    created_at: datetime
    updated_at: datetime
    version: int

    model_config = {"from_attributes": True}

    @field_validator("condition_value", mode="before")
    @classmethod
    def decimal_to_str(cls, v: Any) -> str:
        return str(v)


class ApprovalRuleListResponse(BaseModel):
    """List of approval rules."""

    items: list[ApprovalRuleResponse]


class ApprovalDelegationCreate(BaseModel):
    """Request body for creating an approval delegation."""

    delegator_id: str
    delegate_id: str
    start_date: date
    end_date: date

    @model_validator(mode="after")
    def end_not_before_start(self) -> ApprovalDelegationCreate:
        if self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        return self

    @model_validator(mode="after")
    def no_self_delegation(self) -> ApprovalDelegationCreate:
        if self.delegator_id == self.delegate_id:
            raise ValueError("Cannot delegate to yourself")
        return self


class ApprovalDelegationResponse(BaseModel):
    """Response for an approval delegation."""

    id: str
    tenant_id: str
    delegator_id: str
    delegate_id: str
    start_date: date
    end_date: date
    is_active: bool
    created_at: datetime
    updated_at: datetime
    version: int

    model_config = {"from_attributes": True}


class ApprovalDelegationListResponse(BaseModel):
    """List of approval delegations."""

    items: list[ApprovalDelegationResponse]


class ApproveRejectRequest(BaseModel):
    """Optional comment when approving or rejecting."""

    comment: str | None = Field(default=None, max_length=1000)


# ── Projects & Time Tracking (Issue #67) ─────────────────────────────────


class ProjectCreate(BaseModel):
    contact_id: str
    name: str = Field(..., min_length=1, max_length=200)
    code: str | None = Field(default=None, max_length=50)
    description: str | None = None
    status: str = Field(default="active", pattern="^(active|completed|archived)$")
    budget_hours: str | None = None
    budget_amount: str | None = None
    currency: str = Field(default="USD", min_length=3, max_length=3)

    @field_validator("budget_hours")
    @classmethod
    def budget_hours_non_negative(cls, v: str | None) -> str | None:
        if v is not None and Decimal(v) < 0:
            raise ValueError("budget_hours must be non-negative")
        return v

    @field_validator("budget_amount")
    @classmethod
    def budget_amount_non_negative(cls, v: str | None) -> str | None:
        if v is not None and Decimal(v) < 0:
            raise ValueError("budget_amount must be non-negative")
        return v


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    code: str | None = None
    description: str | None = None
    status: str | None = Field(default=None, pattern="^(active|completed|archived)$")
    budget_hours: str | None = None
    budget_amount: str | None = None
    currency: str | None = Field(default=None, min_length=3, max_length=3)


class ProjectResponse(BaseModel):
    id: str
    contact_id: str
    name: str
    code: str | None
    description: str | None
    status: str
    budget_hours: str | None
    budget_amount: str | None
    currency: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @field_validator("budget_hours", "budget_amount", mode="before")
    @classmethod
    def decimal_to_str_or_none(cls, v: Any) -> str | None:
        return str(v) if v is not None else None


class ProjectListResponse(BaseModel):
    items: list[ProjectResponse]
    next_cursor: str | None


class TimeEntryCreate(BaseModel):
    project_id: str
    user_id: str
    entry_date: date
    hours: str = Field(..., description="Hours as decimal string")
    description: str | None = None
    is_billable: bool = True

    @field_validator("hours")
    @classmethod
    def hours_positive(cls, v: str) -> str:
        if Decimal(v) <= 0:
            raise ValueError("hours must be positive")
        return v


class TimeEntryUpdate(BaseModel):
    hours: str | None = None
    description: str | None = None
    is_billable: bool | None = None
    approval_status: str | None = Field(
        default=None, pattern="^(pending|approved|rejected)$"
    )
    entry_date: date | None = None

    @field_validator("hours")
    @classmethod
    def hours_positive(cls, v: str | None) -> str | None:
        if v is not None and Decimal(v) <= 0:
            raise ValueError("hours must be positive")
        return v


class TimeEntryResponse(BaseModel):
    id: str
    project_id: str
    user_id: str
    entry_date: date
    hours: str
    description: str | None
    is_billable: bool
    approval_status: str
    billed_invoice_id: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @field_validator("hours", mode="before")
    @classmethod
    def decimal_to_str(cls, v: Any) -> str:
        return str(v)


class TimeEntryListResponse(BaseModel):
    items: list[TimeEntryResponse]
    next_cursor: str | None


class BillingRateCreate(BaseModel):
    rate: str = Field(..., description="Rate as decimal string")
    effective_from: date
    effective_to: date | None = None
    project_id: str | None = None
    user_id: str | None = None
    role: str | None = Field(default=None, max_length=50)
    currency: str = Field(default="USD", min_length=3, max_length=3)

    @field_validator("rate")
    @classmethod
    def rate_non_negative(cls, v: str) -> str:
        if Decimal(v) < 0:
            raise ValueError("rate must be non-negative")
        return v


class BillingRateResponse(BaseModel):
    id: str
    project_id: str | None
    user_id: str | None
    role: str | None
    rate: str
    currency: str
    effective_from: date
    effective_to: date | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @field_validator("rate", mode="before")
    @classmethod
    def decimal_to_str(cls, v: Any) -> str:
        return str(v)


class BillingRateListResponse(BaseModel):
    items: list[BillingRateResponse]
    next_cursor: str | None


class GenerateInvoiceRequest(BaseModel):
    from_date: date
    to_date: date

    @model_validator(mode="after")
    def dates_ordered(self) -> GenerateInvoiceRequest:
        if self.to_date < self.from_date:
            raise ValueError("to_date must be on or after from_date")
        return self


class WipEntryResponse(BaseModel):
    id: str
    entry_date: str
    user_id: str
    hours: str
    rate: str
    amount: str
    description: str | None


class WipResponse(BaseModel):
    project_id: str
    entries: list[WipEntryResponse]
    total_hours: str
    total_amount: str
    currency: str
