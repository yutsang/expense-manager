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
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
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
    from datetime import timezone
    return datetime.now(tz=timezone.utc)


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
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="trial")
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, default=_now)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, default=_now)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    __table_args__ = (
        CheckConstraint("status IN ('trial','active','suspended','closed')", name="ck_tenants_status"),
    )


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(254), nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    locale: Mapped[str] = mapped_column(String(10), nullable=False, default="en")
    password_hash: Mapped[str] = mapped_column(String(512), nullable=False)
    email_verified_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    mfa_totp_secret_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    login_failure_count: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    last_login_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, default=_now)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, default=_now)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class Membership(Base):
    __tablename__ = "memberships"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="invited")
    invited_by: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    invited_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    joined_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, default=_now)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, default=_now)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    __table_args__ = (
        UniqueConstraint("tenant_id", "user_id", name="uq_memberships_tenant_user"),
        CheckConstraint("role IN ('owner','admin','accountant','bookkeeper','approver','viewer','auditor','api_client')", name="ck_memberships_role"),
        CheckConstraint("status IN ('invited','active','suspended')", name="ck_memberships_status"),
    )


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    refresh_token_hash: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, default=_now)


class Invite(Base):
    __tablename__ = "invites"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(254), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(256), nullable=False, unique=True)
    invited_by: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, default=_now)


class FeatureFlag(Base):
    __tablename__ = "feature_flags"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    flag: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    enabled_global: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, default=_now)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, default=_now)


class FeatureFlagOverride(Base):
    __tablename__ = "feature_flag_overrides"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    flag: Mapped[str] = mapped_column(String(64), nullable=False)
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, default=_now)

    __table_args__ = (
        UniqueConstraint("flag", "tenant_id", name="uq_flag_overrides_flag_tenant"),
    )


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    tenant_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True, index=True)
    occurred_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, index=True)
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
        CheckConstraint("actor_type IN ('user','system','ai','integration')", name="ck_audit_actor_type"),
    )


# ── Phase 1: Core Ledger ──────────────────────────────────────────────────────

class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[str] = mapped_column(String(16), nullable=False)
    subtype: Mapped[str] = mapped_column(String(32), nullable=False)
    normal_balance: Mapped[str] = mapped_column(String(6), nullable=False)
    parent_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, default=_now)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, default=_now)
    created_by: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    updated_by: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_accounts_tenant_code"),
        CheckConstraint("type IN ('asset','liability','equity','revenue','expense')", name="ck_accounts_type"),
        CheckConstraint("normal_balance IN ('debit','credit')", name="ck_accounts_normal_balance"),
    )


class Period(Base):
    __tablename__ = "periods"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False, index=True)
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
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, default=_now)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, default=_now)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_periods_tenant_name"),
        CheckConstraint("status IN ('open','soft_closed','hard_closed','audited')", name="ck_periods_status"),
    )


class FxRate(Base):
    __tablename__ = "fx_rates"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    from_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    to_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    rate_date: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    rate: Mapped[object] = mapped_column(Numeric(19, 8), nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False, default="manual")
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, default=_now)

    __table_args__ = (
        UniqueConstraint("from_currency", "to_currency", "rate_date", name="uq_fx_rates_pair_date"),
    )


class JournalEntry(Base):
    __tablename__ = "journal_entries"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False, index=True)
    number: Mapped[str] = mapped_column(String(32), nullable=False)
    date: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    period_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("periods.id", ondelete="RESTRICT"), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    source_type: Mapped[str] = mapped_column(String(32), nullable=False, default="manual")
    source_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    void_of: Mapped[str | None] = mapped_column(UUID(as_uuid=False), ForeignKey("journal_entries.id", ondelete="RESTRICT"), nullable=True)
    fx_rate_date: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    total_debit: Mapped[object] = mapped_column(Numeric(19, 4), nullable=False, default=0)
    total_credit: Mapped[object] = mapped_column(Numeric(19, 4), nullable=False, default=0)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    posted_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    posted_by: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, default=_now)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, default=_now)
    created_by: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    updated_by: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    __table_args__ = (
        UniqueConstraint("tenant_id", "number", name="uq_je_tenant_number"),
        CheckConstraint("status IN ('draft','posted','void')", name="ck_je_status"),
    )


class JournalLine(Base):
    __tablename__ = "journal_lines"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False, index=True)
    journal_entry_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("journal_entries.id", ondelete="CASCADE"), nullable=False, index=True)
    line_no: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    account_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False, index=True)
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
