from __future__ import annotations

from functools import lru_cache

from pydantic import Field, RedisDsn, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # App
    app_name: str = "Aegis ERP"
    environment: str = Field("development", pattern="^(development|testing|staging|production)$")
    debug: bool = False
    secret_key: str  # 32-byte hex; used for signing tokens

    # Database (str to support Cloud SQL Unix socket URLs: postgresql+asyncpg://user:pass@/db?host=/cloudsql/...)
    database_url: str
    database_pool_size: int = 10
    database_max_overflow: int = 20

    # Redis
    redis_url: RedisDsn = Field(default="redis://localhost:6379/0")  # type: ignore[assignment]

    # JWT
    jwt_access_token_expire_minutes: int = 15
    jwt_refresh_token_expire_days: int = 30
    jwt_algorithm: str = "HS256"

    # AI — Anthropic (primary, per CLAUDE.md §11.1) and DeepSeek (legacy fallback)
    anthropic_api_key: str = ""
    ai_model_default: str = "claude-sonnet-4-6"
    ai_model_deep: str = "claude-opus-4-6"
    ai_model_fast: str = "claude-haiku-4-5-20251001"
    deepseek_api_key: str = ""

    # S3 / MinIO
    s3_endpoint_url: str = "http://localhost:9000"
    s3_access_key: str = "minioadmin"
    s3_secret_key: str = "minioadmin"  # noqa: S105
    s3_bucket_documents: str = "aegis-documents"
    s3_bucket_exports: str = "aegis-exports"
    s3_region: str = "us-east-1"

    # Email — Resend API
    resend_api_key: str = ""
    email_from: str = "noreply@aegis-erp.com"

    # Email (SMTP)
    smtp_host: str = "localhost"
    smtp_port: int = 1025  # Mailhog dev default
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from: str = "noreply@aegis.local"
    smtp_tls: bool = False

    # Sentry
    sentry_dsn: str = ""

    # OTLP
    otel_exporter_otlp_endpoint: str = ""

    # Feature flags
    feature_flag_ai_enabled: bool = True

    @model_validator(mode="after")
    def validate_secret_key(self) -> Settings:
        if len(self.secret_key) < 32:
            raise ValueError("secret_key must be at least 32 characters")
        return self

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def is_testing(self) -> bool:
        return self.environment == "testing"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
