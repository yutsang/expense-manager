"""SQLAlchemy ORM model definitions.

All business tables must be registered here so that:
  - alembic/env.py can see them for autogenerate
  - The audit emitter and repos can use them
  - Type checking works end-to-end

Rules:
  - Every tenant-scoped table has tenant_id (NOT NULL).
  - Money columns: Numeric(19, 4) + a paired currency column.
  - id: UUID (server default gen_random_uuid()).
  - Always include: created_at, updated_at, version (optimistic lock).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import sqlalchemy as sa
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Integer,
    LargeBinary,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(tz=UTC)


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    legal_name: Mapped[str] = mapped_column(String(255), nullable=False)
    country: Mapped[str] = mapped_column(String(10), nullable=False)
    functional_currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    fiscal_year_start_month: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="UTC")
    region: Mapped[str] = mapped_column(String(16), nullable=False, default="us")
    invoice_approval_threshold: Mapped[object | None] = mapped_column(Numeric(19, 4), nullable=True)
    invoice_number_seq: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    journal_approval_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="trial")
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=_now
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    setup_completed_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('trial','active','suspended','closed')", name="ck_tenants_status"
        ),
    )


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(254), nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    locale: Mapped[str] = mapped_column(String(10), nullable=False, default="en")
    password_hash: Mapped[str] = mapped_column(String(512), nullable=False)
    email_verified_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    mfa_totp_secret_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    login_failure_count: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    last_login_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=_now
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class Membership(Base):
    __tablename__ = "memberships"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="invited")
    invited_by: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    invited_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    joined_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=_now
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    __table_args__ = (
        UniqueConstraint("tenant_id", "user_id", name="uq_memberships_tenant_user"),
        CheckConstraint(
            "role IN ('owner','admin','accountant','bookkeeper','approver','viewer','auditor','api_client')",
            name="ck_memberships_role",
        ),
        CheckConstraint("status IN ('invited','active','suspended')", name="ck_memberships_status"),
    )


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    refresh_token_hash: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=_now
    )


class Invite(Base):
    __tablename__ = "invites"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    email: Mapped[str] = mapped_column(String(254), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(256), nullable=False, unique=True)
    invited_by: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=_now
    )


class FeatureFlag(Base):
    __tablename__ = "feature_flags"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    flag: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    enabled_global: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=_now
    )


class FeatureFlagOverride(Base):
    __tablename__ = "feature_flag_overrides"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    flag: Mapped[str] = mapped_column(String(64), nullable=False)
    tenant_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=_now
    )

    __table_args__ = (UniqueConstraint("flag", "tenant_id", name="uq_flag_overrides_flag_tenant"),)


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    tenant_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True, index=True)
    occurred_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, index=True
    )
    actor_type: Mapped[str] = mapped_column(String(16), nullable=False)
    actor_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True, index=True)
    session_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    before_state: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    after_state: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    metadata_: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    prev_hash: Mapped[bytes] = mapped_column(LargeBinary(32), nullable=False)
    hash: Mapped[bytes] = mapped_column(LargeBinary(32), nullable=False)

    __table_args__ = (
        CheckConstraint(
            "actor_type IN ('user','system','ai','integration')", name="ck_audit_actor_type"
        ),
    )


# ── Phase 1: Core Ledger ──────────────────────────────────────────────────────


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    code: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[str] = mapped_column(String(16), nullable=False)
    subtype: Mapped[str] = mapped_column(String(32), nullable=False)
    normal_balance: Mapped[str] = mapped_column(String(6), nullable=False)
    parent_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("accounts.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_control_account: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=_now
    )
    created_by: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    updated_by: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_accounts_tenant_code"),
        CheckConstraint(
            "type IN ('asset','liability','equity','revenue','expense')", name="ck_accounts_type"
        ),
        CheckConstraint("normal_balance IN ('debit','credit')", name="ck_accounts_normal_balance"),
    )


class Period(Base):
    __tablename__ = "periods"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(20), nullable=False)
    start_date: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    end_date: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open")
    closed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    closed_by: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    closed_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    reopened_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    reopened_by: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    reopened_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=_now
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_periods_tenant_name"),
        CheckConstraint(
            "status IN ('open','soft_closed','hard_closed','audited')", name="ck_periods_status"
        ),
    )


class FxRate(Base):
    __tablename__ = "fx_rates"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    from_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    to_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    rate_date: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    rate: Mapped[object] = mapped_column(Numeric(19, 8), nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False, default="manual")
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=_now
    )

    __table_args__ = (
        UniqueConstraint("from_currency", "to_currency", "rate_date", name="uq_fx_rates_pair_date"),
    )


class JournalEntry(Base):
    __tablename__ = "journal_entries"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    number: Mapped[str] = mapped_column(String(32), nullable=False)
    date: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    period_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("periods.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    source_type: Mapped[str] = mapped_column(String(32), nullable=False, default="manual")
    source_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    void_of: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("journal_entries.id", ondelete="RESTRICT"), nullable=True
    )
    fx_rate_date: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    total_debit: Mapped[object] = mapped_column(Numeric(19, 4), nullable=False, default=0)
    total_credit: Mapped[object] = mapped_column(Numeric(19, 4), nullable=False, default=0)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    submitted_by: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    approved_by: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    posted_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    posted_by: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=_now
    )
    created_by: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    updated_by: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(256), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    __table_args__ = (
        UniqueConstraint("tenant_id", "number", name="uq_je_tenant_number"),
        CheckConstraint(
            "status IN ('draft','awaiting_approval','posted','void')", name="ck_je_status"
        ),
        sa.Index("ix_je_idempotency", "tenant_id", "idempotency_key"),
    )


class JournalLine(Base):
    __tablename__ = "journal_lines"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False, index=True)
    journal_entry_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("journal_entries.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    line_no: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    account_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("accounts.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    contact_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    debit: Mapped[object] = mapped_column(Numeric(19, 4), nullable=False, default=0)
    credit: Mapped[object] = mapped_column(Numeric(19, 4), nullable=False, default=0)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    fx_rate: Mapped[object | None] = mapped_column(Numeric(19, 8), nullable=True)
    functional_debit: Mapped[object] = mapped_column(Numeric(19, 4), nullable=False, default=0)
    functional_credit: Mapped[object] = mapped_column(Numeric(19, 4), nullable=False, default=0)

    __table_args__ = (
        UniqueConstraint("journal_entry_id", "line_no", name="uq_jl_entry_line"),
        CheckConstraint("debit >= 0 AND credit >= 0", name="ck_jl_non_negative"),
    )


# ---------------------------------------------------------------------------
# Phase 2 — Transactions, Contacts, Items, Tax, Invoices, Bills, Payments
# ---------------------------------------------------------------------------


class Contact(Base):
    """Customers, suppliers, or employees — shared namespace per tenant."""

    __tablename__ = "contacts"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False, index=True)
    contact_type: Mapped[str] = mapped_column(
        String(16), nullable=False
    )  # customer|supplier|both|employee
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    tax_number: Mapped[str | None] = mapped_column(String(64), nullable=True)  # ABN/VAT reg etc.
    # Address (denormalised — one primary)
    address_line1: Mapped[str | None] = mapped_column(String(255), nullable=True)
    address_line2: Mapped[str | None] = mapped_column(String(255), nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    region: Mapped[str | None] = mapped_column(String(100), nullable=True)
    postal_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    country: Mapped[str | None] = mapped_column(String(10), nullable=True)
    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    credit_limit: Mapped[object | None] = mapped_column(Numeric(19, 4), nullable=True)
    # AMLO Cap 615 — DNFBP risk classification
    risk_rating: Mapped[str | None] = mapped_column(
        String(16), nullable=True
    )  # low|medium|high|unacceptable
    risk_rating_rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    risk_rated_by: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    risk_rated_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    edd_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    edd_approved_by: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    edd_approved_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=_now
    )
    created_by: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    updated_by: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_contacts_tenant_code"),
        CheckConstraint(
            "contact_type IN ('customer','supplier','both','employee')",
            name="ck_contacts_type",
        ),
        CheckConstraint(
            "risk_rating IN ('low','medium','high','unacceptable') OR risk_rating IS NULL",
            name="ck_contacts_risk_rating",
        ),
    )


class ContactKyc(Base):
    """KYC / sanctions record for a contact (one per contact per tenant)."""

    __tablename__ = "contact_kyc"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False, index=True)
    contact_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("contacts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    id_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    id_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    id_expiry_date: Mapped[object | None] = mapped_column(Date, nullable=True)
    poa_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    poa_date: Mapped[object | None] = mapped_column(Date, nullable=True)
    sanctions_status: Mapped[str] = mapped_column(String(20), nullable=False, default="not_checked")
    sanctions_checked_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    kyc_status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    kyc_approved_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    kyc_approved_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    last_review_date: Mapped[object | None] = mapped_column(Date, nullable=True)
    next_review_date: Mapped[object | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=_now
    )
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    updated_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    __table_args__ = (
        UniqueConstraint("tenant_id", "contact_id", name="uq_contact_kyc_tenant_contact"),
        CheckConstraint(
            "id_type IN ('passport','national_id','drivers_license','other') OR id_type IS NULL",
            name="ck_kyc_id_type",
        ),
        CheckConstraint(
            "poa_type IN ('utility_bill','bank_statement','tax_document','other') OR poa_type IS NULL",
            name="ck_kyc_poa_type",
        ),
        CheckConstraint(
            "sanctions_status IN ('not_checked','clear','flagged','under_review')",
            name="ck_kyc_sanctions_status",
        ),
        CheckConstraint(
            "kyc_status IN ('pending','approved','expired','flagged')",
            name="ck_kyc_status",
        ),
    )


class ContactUBO(Base):
    """Ultimate Beneficial Owner / Significant Controller per HK Cap 622."""

    __tablename__ = "contact_ubos"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False, index=True)
    contact_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("contacts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    controller_name: Mapped[str] = mapped_column(String(255), nullable=False)
    id_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    id_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    nationality: Mapped[str | None] = mapped_column(String(10), nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    ownership_pct: Mapped[object] = mapped_column(Numeric(5, 2), nullable=False)
    control_type: Mapped[str] = mapped_column(String(32), nullable=False)
    is_significant_controller: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    effective_date: Mapped[object] = mapped_column(Date, nullable=False)
    ceased_date: Mapped[object | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=_now
    )
    created_by: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    updated_by: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    __table_args__ = (
        CheckConstraint(
            "control_type IN ('shareholding','voting_rights','board_appointment','other')",
            name="ck_contact_ubos_control_type",
        ),
        CheckConstraint(
            "ownership_pct >= 0 AND ownership_pct <= 100",
            name="ck_contact_ubos_ownership_pct",
        ),
    )


class Item(Base):
    """Products or services that appear on invoice/bill lines."""

    __tablename__ = "items"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    item_type: Mapped[str] = mapped_column(String(16), nullable=False)  # product|service
    unit_of_measure: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # Default prices (can be overridden per line)
    sales_unit_price: Mapped[object | None] = mapped_column(Numeric(19, 4), nullable=True)
    purchase_unit_price: Mapped[object | None] = mapped_column(Numeric(19, 4), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    # Default GL accounts
    sales_account_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True
    )
    cogs_account_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True
    )
    purchase_account_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True
    )
    is_tracked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=_now
    )
    created_by: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    updated_by: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_items_tenant_code"),
        CheckConstraint("item_type IN ('product','service')", name="ck_items_type"),
    )


class TaxCode(Base):
    """Tax rate definitions (GST, VAT, Sales Tax, etc.)."""

    __tablename__ = "tax_codes"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(32), nullable=False)  # e.g. GST, VAT20, ZERO
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    rate: Mapped[object] = mapped_column(Numeric(8, 6), nullable=False)  # e.g. 0.100000 = 10%
    tax_type: Mapped[str] = mapped_column(String(16), nullable=False)  # output|input|exempt|zero
    country: Mapped[str] = mapped_column(String(10), nullable=False)
    # GL accounts for tax collected / tax paid
    tax_collected_account_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True
    )
    tax_paid_account_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=_now
    )
    created_by: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    updated_by: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_tax_codes_tenant_code"),
        CheckConstraint(
            "tax_type IN ('output','input','exempt','zero')",
            name="ck_tax_codes_type",
        ),
        CheckConstraint("rate >= 0 AND rate <= 1", name="ck_tax_codes_rate"),
    )


class Invoice(Base):
    """Sales invoices issued to customers."""

    __tablename__ = "invoices"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False, index=True)
    number: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    # draft | awaiting_approval | authorised | sent | partial | paid | void | credit_note
    authorised_by: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    contact_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("contacts.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    issue_date: Mapped[str] = mapped_column(String(10), nullable=False)  # ISO date string
    due_date: Mapped[str | None] = mapped_column(String(10), nullable=True)
    period_name: Mapped[str | None] = mapped_column(String(7), nullable=True)
    reference: Mapped[str | None] = mapped_column(String(128), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    fx_rate: Mapped[object] = mapped_column(Numeric(19, 8), nullable=False, default=1)
    subtotal: Mapped[object] = mapped_column(Numeric(19, 4), nullable=False, default=0)
    tax_total: Mapped[object] = mapped_column(Numeric(19, 4), nullable=False, default=0)
    total: Mapped[object] = mapped_column(Numeric(19, 4), nullable=False, default=0)
    amount_due: Mapped[object] = mapped_column(Numeric(19, 4), nullable=False, default=0)
    functional_total: Mapped[object] = mapped_column(Numeric(19, 4), nullable=False, default=0)
    # GL journal posted when authorised
    journal_entry_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("journal_entries.id", ondelete="SET NULL"), nullable=True
    )
    # Links a credit note to the original invoice it reverses
    credit_note_for_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("invoices.id", ondelete="SET NULL"), nullable=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    voided_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    last_reminder_sent_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    reminder_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Customer portal (Issue #36)
    share_token: Mapped[str | None] = mapped_column(String(256), nullable=True, unique=True)
    viewed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    acknowledged_by_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=_now
    )
    created_by: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    updated_by: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    __table_args__ = (
        UniqueConstraint("tenant_id", "number", name="uq_invoices_tenant_number"),
        CheckConstraint(
            "status IN ('draft','awaiting_approval','authorised','sent','partial','paid','void','credit_note')",
            name="ck_invoices_status",
        ),
    )


class InvoiceLine(Base):
    """Line items on a sales invoice."""

    __tablename__ = "invoice_lines"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False, index=True)
    invoice_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("invoices.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    line_no: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    item_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("items.id", ondelete="SET NULL"), nullable=True
    )
    account_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False
    )
    tax_code_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("tax_codes.id", ondelete="SET NULL"), nullable=True
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    quantity: Mapped[object] = mapped_column(Numeric(19, 4), nullable=False, default=1)
    unit_price: Mapped[object] = mapped_column(Numeric(19, 4), nullable=False, default=0)
    discount_pct: Mapped[object] = mapped_column(
        Numeric(5, 4), nullable=False, default=0
    )  # 0.1 = 10%
    line_amount: Mapped[object] = mapped_column(Numeric(19, 4), nullable=False, default=0)
    tax_amount: Mapped[object] = mapped_column(Numeric(19, 4), nullable=False, default=0)

    __table_args__ = (
        UniqueConstraint("invoice_id", "line_no", name="uq_inv_line_no"),
        CheckConstraint("quantity > 0", name="ck_invline_qty"),
        CheckConstraint("discount_pct >= 0 AND discount_pct < 1", name="ck_invline_discount"),
    )


class Bill(Base):
    """Purchase bills received from suppliers."""

    __tablename__ = "bills"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False, index=True)
    number: Mapped[str] = mapped_column(String(64), nullable=False)
    supplier_reference: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    # draft | awaiting_approval | approved | partial | paid | void
    contact_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("contacts.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    issue_date: Mapped[str] = mapped_column(String(10), nullable=False)
    due_date: Mapped[str | None] = mapped_column(String(10), nullable=True)
    period_name: Mapped[str | None] = mapped_column(String(7), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    fx_rate: Mapped[object] = mapped_column(Numeric(19, 8), nullable=False, default=1)
    subtotal: Mapped[object] = mapped_column(Numeric(19, 4), nullable=False, default=0)
    tax_total: Mapped[object] = mapped_column(Numeric(19, 4), nullable=False, default=0)
    total: Mapped[object] = mapped_column(Numeric(19, 4), nullable=False, default=0)
    amount_due: Mapped[object] = mapped_column(Numeric(19, 4), nullable=False, default=0)
    functional_total: Mapped[object] = mapped_column(Numeric(19, 4), nullable=False, default=0)
    journal_entry_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("journal_entries.id", ondelete="SET NULL"), nullable=True
    )
    approved_by: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=_now
    )
    created_by: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    updated_by: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    __table_args__ = (
        UniqueConstraint("tenant_id", "number", name="uq_bills_tenant_number"),
        CheckConstraint(
            "status IN ('draft','awaiting_approval','approved','partial','paid','void')",
            name="ck_bills_status",
        ),
    )


class BillLine(Base):
    """Line items on a purchase bill."""

    __tablename__ = "bill_lines"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False, index=True)
    bill_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("bills.id", ondelete="CASCADE"), nullable=False, index=True
    )
    line_no: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    item_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("items.id", ondelete="SET NULL"), nullable=True
    )
    account_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False
    )
    tax_code_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("tax_codes.id", ondelete="SET NULL"), nullable=True
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    quantity: Mapped[object] = mapped_column(Numeric(19, 4), nullable=False, default=1)
    unit_price: Mapped[object] = mapped_column(Numeric(19, 4), nullable=False, default=0)
    discount_pct: Mapped[object] = mapped_column(Numeric(5, 4), nullable=False, default=0)
    line_amount: Mapped[object] = mapped_column(Numeric(19, 4), nullable=False, default=0)
    tax_amount: Mapped[object] = mapped_column(Numeric(19, 4), nullable=False, default=0)

    __table_args__ = (
        UniqueConstraint("bill_id", "line_no", name="uq_bill_line_no"),
        CheckConstraint("quantity > 0", name="ck_billline_qty"),
        CheckConstraint("discount_pct >= 0 AND discount_pct < 1", name="ck_billline_discount"),
    )


class Payment(Base):
    """A payment received (from customer) or made (to supplier)."""

    __tablename__ = "payments"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False, index=True)
    number: Mapped[str] = mapped_column(String(64), nullable=False)
    payment_type: Mapped[str] = mapped_column(String(16), nullable=False)  # received|made
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending"
    )  # pending|applied|voided
    contact_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("contacts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    payment_date: Mapped[str] = mapped_column(String(10), nullable=False)
    amount: Mapped[object] = mapped_column(Numeric(19, 4), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    fx_rate: Mapped[object] = mapped_column(Numeric(19, 8), nullable=False, default=1)
    functional_amount: Mapped[object] = mapped_column(Numeric(19, 4), nullable=False)
    # Bank account from which payment was made / received
    bank_account_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True
    )
    reference: Mapped[str | None] = mapped_column(String(128), nullable=True)
    journal_entry_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("journal_entries.id", ondelete="SET NULL"), nullable=True
    )
    idempotency_key: Mapped[str | None] = mapped_column(String(256), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=_now
    )
    created_by: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    updated_by: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    __table_args__ = (
        UniqueConstraint("tenant_id", "number", name="uq_payments_tenant_number"),
        CheckConstraint("payment_type IN ('received','made')", name="ck_payments_type"),
        CheckConstraint("status IN ('pending','applied','voided')", name="ck_payments_status"),
        CheckConstraint("amount > 0", name="ck_payments_positive"),
        sa.Index("ix_payments_idempotency", "tenant_id", "idempotency_key"),
    )


class PaymentAllocation(Base):
    """Links a payment to one or more invoices/bills (supports partial payments)."""

    __tablename__ = "payment_allocations"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False, index=True)
    payment_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("payments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Exactly one of invoice_id or bill_id is set
    invoice_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("invoices.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    bill_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("bills.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    amount: Mapped[object] = mapped_column(Numeric(19, 4), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=_now
    )
    created_by: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)

    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_palloc_positive"),
        CheckConstraint(
            "(invoice_id IS NOT NULL AND bill_id IS NULL) OR (invoice_id IS NULL AND bill_id IS NOT NULL)",
            name="ck_palloc_exclusive",
        ),
    )


# ---------------------------------------------------------------------------
# Phase 2 — Bank Accounts, Bank Transactions, Bank Reconciliations,
#            Expense Claims
# ---------------------------------------------------------------------------


class BankAccount(Base):
    """A bank or cash account linked to a Chart of Accounts entry."""

    __tablename__ = "bank_accounts"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    bank_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    account_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    coa_account_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_reconciled_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    last_reconciled_balance: Mapped[object | None] = mapped_column(Numeric(19, 4), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=_now
    )
    created_by: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    updated_by: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class BankTransaction(Base):
    """An individual line on a bank statement."""

    __tablename__ = "bank_transactions"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False, index=True)
    bank_account_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("bank_accounts.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    transaction_date: Mapped[datetime] = mapped_column(Date, nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    reference: Mapped[str | None] = mapped_column(String(200), nullable=True)
    amount: Mapped[object] = mapped_column(
        Numeric(19, 4), nullable=False
    )  # positive = in, negative = out
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    is_reconciled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    reconciled_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    journal_line_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("journal_lines.id", ondelete="RESTRICT"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=_now
    )
    created_by: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    updated_by: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class BankReconciliation(Base):
    """A completed or in-progress bank reconciliation snapshot."""

    __tablename__ = "bank_reconciliations"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False, index=True)
    bank_account_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("bank_accounts.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    period_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("periods.id", ondelete="RESTRICT"), nullable=True
    )
    statement_closing_balance: Mapped[object] = mapped_column(Numeric(19, 4), nullable=False)
    book_balance: Mapped[object] = mapped_column(Numeric(19, 4), nullable=False)
    difference: Mapped[object] = mapped_column(Numeric(19, 4), nullable=False)  # statement - book
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="in_progress"
    )  # in_progress|completed
    reconciled_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    reconciled_by: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=_now
    )
    created_by: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    updated_by: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    __table_args__ = (
        CheckConstraint("status IN ('in_progress','completed')", name="ck_bank_recon_status"),
    )


class ExpenseClaim(Base):
    """An employee expense claim."""

    __tablename__ = "expense_claims"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False, index=True)
    number: Mapped[str] = mapped_column(String(20), nullable=False)  # EXP-000001
    contact_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("contacts.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    # draft | submitted | approved | rejected | paid
    claim_date: Mapped[datetime] = mapped_column(Date, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    total_amount: Mapped[object] = mapped_column(Numeric(19, 4), nullable=False, default=0)
    tax_total: Mapped[object] = mapped_column(Numeric(19, 4), nullable=False, default=0)
    journal_entry_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("journal_entries.id", ondelete="SET NULL"), nullable=True
    )
    approved_by: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    paid_by: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=_now
    )
    created_by: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    updated_by: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    __table_args__ = (
        UniqueConstraint("tenant_id", "number", name="uq_expense_claims_tenant_number"),
        CheckConstraint(
            "status IN ('draft','submitted','approved','rejected','paid')",
            name="ck_expense_claims_status",
        ),
    )


class ExpenseClaimLine(Base):
    """A line item on an expense claim."""

    __tablename__ = "expense_claim_lines"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False, index=True)
    claim_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("expense_claims.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    account_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False
    )
    tax_code_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("tax_codes.id", ondelete="RESTRICT"), nullable=True
    )
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    amount: Mapped[object] = mapped_column(Numeric(19, 4), nullable=False)
    tax_amount: Mapped[object] = mapped_column(Numeric(19, 4), nullable=False, default=0)
    receipt_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)


# ---------------------------------------------------------------------------
# Phase 3 — AI Assistant: conversations and messages
# ---------------------------------------------------------------------------


class AiConversation(Base):
    """A single chat conversation between a user and the AI assistant."""

    __tablename__ = "ai_conversations"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=_now
    )
    created_by: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    updated_by: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class AiMessage(Base):
    """A single message within an AI conversation."""

    __tablename__ = "ai_messages"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False, index=True)
    conversation_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("ai_conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    tool_calls: Mapped[list | None] = mapped_column(sa.JSON, nullable=True)
    tool_use_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    tool_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(20), nullable=True)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cache_creation_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cache_read_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=_now
    )
    created_by: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    updated_by: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    __table_args__ = (
        CheckConstraint(
            "role IN ('user', 'assistant', 'tool_result')",
            name="ck_ai_messages_role",
        ),
    )


# ---------------------------------------------------------------------------
# Phase 4 — Audit Module: chain verifications and report snapshots
# ---------------------------------------------------------------------------


class AuditChainVerification(Base):
    """Result of a hash-chain verification run for a tenant."""

    __tablename__ = "audit_chain_verifications"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False, index=True)
    verified_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=_now
    )
    chain_length: Mapped[int] = mapped_column(Integer, nullable=False)
    last_event_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    is_valid: Mapped[bool] = mapped_column(Boolean, nullable=False)
    break_at_event_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=_now
    )


class ReportSnapshot(Base):
    """Immutable snapshot of a generated report (sha256-verified)."""

    __tablename__ = "report_snapshots"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False, index=True)
    report_type: Mapped[str] = mapped_column(String(50), nullable=False)
    params: Mapped[dict] = mapped_column(sa.JSON, nullable=False, default=dict)
    generated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=_now
    )
    data: Mapped[dict] = mapped_column(sa.JSON, nullable=False, default=dict)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=_now
    )


# ---------------------------------------------------------------------------
# Phase 5 — Mobile Sync: sync_devices + sync_ops
# ---------------------------------------------------------------------------


class SyncDevice(Base):
    """A registered mobile or web device for sync."""

    __tablename__ = "sync_devices"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    device_fingerprint: Mapped[str] = mapped_column(String(128), nullable=False)
    platform: Mapped[str] = mapped_column(String(10), nullable=False, default="web")
    app_version: Mapped[str | None] = mapped_column(String(20), nullable=True)
    push_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_seen: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=_now
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "device_fingerprint", name="uq_sync_devices_tenant_fp"),
        CheckConstraint("platform IN ('ios','android','web')", name="ck_sync_devices_platform"),
    )


class SyncOp(Base):
    """Server-side record of a client push operation (idempotency log)."""

    __tablename__ = "sync_ops"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False, index=True)
    client_op_id: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    device_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("sync_devices.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    entity_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    entity_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    base_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    applied_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    applied_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=_now
    )

    __table_args__ = (
        CheckConstraint("status IN ('applied','conflict','error')", name="ck_sync_ops_status"),
    )


# ---------------------------------------------------------------------------
# Phase 6 — Sanctions: global reference lists + per-tenant screening results
# ---------------------------------------------------------------------------


class SanctionsListSnapshot(Base):
    """Immutable snapshot of a fetched sanctions list (OFAC or FATF)."""

    __tablename__ = "sanctions_list_snapshots"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    source: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    fetched_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=_now
    )
    entry_count: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class SanctionsListEntry(Base):
    """A single entity/country in a sanctions list snapshot."""

    __tablename__ = "sanctions_list_entries"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    snapshot_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("sanctions_list_snapshots.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    ref_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(20), nullable=False)
    primary_name: Mapped[str] = mapped_column(String(500), nullable=False)
    aliases: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    countries: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    programs: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(50), nullable=False)


class ContactSanctionsResult(Base):
    """Screening result for a contact against all active sanctions lists."""

    __tablename__ = "contact_sanctions_results"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False, index=True)
    contact_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("contacts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    screened_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=_now
    )
    snapshot_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("sanctions_list_snapshots.id", ondelete="SET NULL"),
        nullable=True,
    )
    match_status: Mapped[str] = mapped_column(String(20), nullable=False, default="clear")
    match_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    matched_entry_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("sanctions_list_entries.id", ondelete="SET NULL"),
        nullable=True,
    )
    matched_name: Mapped[str | None] = mapped_column(String(500), nullable=True)
    details: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    __table_args__ = (
        UniqueConstraint("tenant_id", "contact_id", name="uq_sanctions_results_tenant_contact"),
    )


# ---------------------------------------------------------------------------
# Phase 7 — Receipts: OCR via Claude Vision
# ---------------------------------------------------------------------------


class Receipt(Base):
    """A receipt image uploaded by a user, OCR-processed by Claude Vision."""

    __tablename__ = "receipts"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False, index=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    s3_key: Mapped[str] = mapped_column(String(512), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    file_size_kb: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    # OCR extracted fields
    ocr_vendor: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ocr_date: Mapped[str | None] = mapped_column(String(10), nullable=True)
    ocr_currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    ocr_total: Mapped[object | None] = mapped_column(Numeric(19, 4), nullable=True)
    ocr_raw: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    # Link to a bill created from this receipt
    linked_bill_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("bills.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=_now
    )
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','processing','done','failed','deleted')",
            name="ck_receipts_status",
        ),
    )


# ---------------------------------------------------------------------------
# Phase 8 — Sales Chain: SalesDocument (Quote/SalesOrder), PurchaseOrder,
#            Attachment
# ---------------------------------------------------------------------------


class SalesDocument(Base):
    """Quote or Sales Order — doc_type distinguishes them."""

    __tablename__ = "sales_documents"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False, index=True)
    doc_type: Mapped[str] = mapped_column(String(20), nullable=False)  # quote | sales_order
    number: Mapped[str] = mapped_column(String(50), nullable=False)
    contact_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("contacts.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    issue_date: Mapped[str] = mapped_column(String(10), nullable=False)  # ISO date string
    expiry_date: Mapped[str | None] = mapped_column(String(10), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    # draft | sent | accepted | rejected | converted | voided
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    subtotal: Mapped[object] = mapped_column(Numeric(19, 4), nullable=False, default=0)
    tax_total: Mapped[object] = mapped_column(Numeric(19, 4), nullable=False, default=0)
    total: Mapped[object] = mapped_column(Numeric(19, 4), nullable=False, default=0)
    reference: Mapped[str | None] = mapped_column(String(200), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    converted_to_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=_now
    )
    created_by: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    updated_by: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    locked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    lines: Mapped[list[SalesDocumentLine]] = sa.orm.relationship(
        "SalesDocumentLine", back_populates="document", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "number", name="uq_sales_documents_tenant_number"),
        CheckConstraint(
            "doc_type IN ('quote','sales_order')",
            name="ck_sales_documents_type",
        ),
        CheckConstraint(
            "status IN ('draft','sent','accepted','rejected','converted','voided')",
            name="ck_sales_documents_status",
        ),
    )


class SalesDocumentLine(Base):
    """Line items on a sales document (quote or sales order)."""

    __tablename__ = "sales_document_lines"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False, index=True)
    document_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("sales_documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    item_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("items.id", ondelete="SET NULL"), nullable=True
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    quantity: Mapped[object] = mapped_column(Numeric(19, 4), nullable=False, default=1)
    unit_price: Mapped[object] = mapped_column(Numeric(19, 4), nullable=False, default=0)
    tax_rate: Mapped[object] = mapped_column(Numeric(7, 4), nullable=False, default=0)
    line_total: Mapped[object] = mapped_column(Numeric(19, 4), nullable=False, default=0)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    document: Mapped[SalesDocument] = sa.orm.relationship("SalesDocument", back_populates="lines")


class PurchaseOrder(Base):
    """Purchase order sent to a supplier."""

    __tablename__ = "purchase_orders"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False, index=True)
    number: Mapped[str] = mapped_column(String(50), nullable=False)
    contact_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("contacts.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    issue_date: Mapped[str] = mapped_column(String(10), nullable=False)  # ISO date string
    expected_delivery: Mapped[str | None] = mapped_column(String(10), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    # draft | sent | partially_received | received | billed | voided
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    subtotal: Mapped[object] = mapped_column(Numeric(19, 4), nullable=False, default=0)
    tax_total: Mapped[object] = mapped_column(Numeric(19, 4), nullable=False, default=0)
    total: Mapped[object] = mapped_column(Numeric(19, 4), nullable=False, default=0)
    reference: Mapped[str | None] = mapped_column(String(200), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    linked_bill_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=_now
    )
    created_by: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    updated_by: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    locked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    lines: Mapped[list[PurchaseOrderLine]] = sa.orm.relationship(
        "PurchaseOrderLine", back_populates="po", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "number", name="uq_purchase_orders_tenant_number"),
        CheckConstraint(
            "status IN ('draft','sent','partially_received','received','billed','voided')",
            name="ck_purchase_orders_status",
        ),
    )


class PurchaseOrderLine(Base):
    """Line items on a purchase order."""

    __tablename__ = "purchase_order_lines"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False, index=True)
    po_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("purchase_orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    item_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("items.id", ondelete="SET NULL"), nullable=True
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    quantity: Mapped[object] = mapped_column(Numeric(19, 4), nullable=False, default=1)
    unit_price: Mapped[object] = mapped_column(Numeric(19, 4), nullable=False, default=0)
    tax_rate: Mapped[object] = mapped_column(Numeric(7, 4), nullable=False, default=0)
    line_total: Mapped[object] = mapped_column(Numeric(19, 4), nullable=False, default=0)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    po: Mapped[PurchaseOrder] = sa.orm.relationship("PurchaseOrder", back_populates="lines")


class PeriodChecklistItem(Base):
    """Sign-off record for a period close checklist task."""

    __tablename__ = "period_checklist_items"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False, index=True)
    period_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("periods.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    task_key: Mapped[str] = mapped_column(String(64), nullable=False)
    checked_by: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    checked_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=_now
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    __table_args__ = (
        UniqueConstraint("period_id", "task_key", name="uq_period_checklist_period_task"),
    )


class Attachment(Base):
    """Generic file attachment — can be linked to any document type."""

    __tablename__ = "attachments"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    # invoice | bill | po | sales_document | payment | journal_entry
    entity_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    s3_key: Mapped[str] = mapped_column(String(500), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    file_size_kb: Mapped[int] = mapped_column(Integer, nullable=False)
    uploaded_by: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=_now
    )


# ---------------------------------------------------------------------------
# Issue #42 — Accruals and Prepayments
# ---------------------------------------------------------------------------


class Accrual(Base):
    """Accrual or prepayment with automatic reversal in the next period."""

    __tablename__ = "accruals"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False, index=True)
    accrual_type: Mapped[str] = mapped_column(String(16), nullable=False)  # accrual | prepayment
    description: Mapped[str] = mapped_column(Text, nullable=False)
    amount: Mapped[object] = mapped_column(Numeric(19, 4), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    debit_account_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("accounts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    credit_account_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("accounts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    period_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("periods.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    journal_entry_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("journal_entries.id", ondelete="SET NULL"),
        nullable=True,
    )
    reversal_journal_entry_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("journal_entries.id", ondelete="SET NULL"),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="posted"
    )  # posted | reversed
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=_now
    )
    created_by: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    updated_by: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    __table_args__ = (
        CheckConstraint(
            "accrual_type IN ('accrual','prepayment')", name="ck_accruals_type"
        ),
        CheckConstraint(
            "status IN ('posted','reversed')", name="ck_accruals_status"
        ),
        CheckConstraint("amount > 0", name="ck_accruals_positive"),
    )
