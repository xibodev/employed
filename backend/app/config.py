from __future__ import annotations

from functools import lru_cache

from pydantic import Field, computed_field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = Field(default="Employed API", alias="APP_NAME")
    environment: str = Field(default="development", alias="ENVIRONMENT")
    debug: bool = Field(default=False, alias="DEBUG")
    secret_key: str | None = Field(default=None, alias="SECRET_KEY")
    database_url: str = Field(
        default="postgresql+psycopg2://postgres:postgres@localhost:5432/employed",
        alias="DATABASE_URL",
    )
    redis_url: str | None = Field(default=None, alias="REDIS_URL")
    alembic_database_url: str | None = Field(default=None, alias="ALEMBIC_DATABASE_URL")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    database_pool_size: int = Field(default=5, alias="DATABASE_POOL_SIZE")
    database_max_overflow: int = Field(default=10, alias="DATABASE_MAX_OVERFLOW")
    database_pool_timeout: int = Field(default=30, alias="DATABASE_POOL_TIMEOUT")
    database_pool_recycle: int = Field(default=1800, alias="DATABASE_POOL_RECYCLE")

    # Email / SMTP
    smtp_host: str | None = Field(default=None, alias="SMTP_HOST")
    smtp_port: int = Field(default=587, alias="SMTP_PORT")
    smtp_username: str | None = Field(default=None, alias="SMTP_USERNAME")
    smtp_password: str | None = Field(default=None, alias="SMTP_PASSWORD")
    smtp_use_tls: bool = Field(default=False, alias="SMTP_USE_TLS")
    smtp_use_ssl: bool = Field(default=False, alias="SMTP_USE_SSL")
    email_from: str | None = Field(default=None, alias="FROM_EMAIL")

    # Stripe (Resend-style: declared even though adapters read via _setting helper,
    # so pydantic-settings hydrates the values instead of silently dropping them).
    stripe_secret_key: str | None = Field(default=None, alias="STRIPE_SECRET_KEY")
    stripe_publishable_key: str | None = Field(default=None, alias="STRIPE_PUBLISHABLE_KEY")
    stripe_webhook_secret: str | None = Field(default=None, alias="STRIPE_WEBHOOK_SECRET")

    # reCAPTCHA (server-side verification + frontend site key passthrough)
    recaptcha_secret_key: str | None = Field(default=None, alias="RECAPTCHA_SECRET_KEY")
    next_public_recaptcha_site_key: str | None = Field(default=None, alias="NEXT_PUBLIC_RECAPTCHA_SITE_KEY")
    recaptcha_min_score: float = Field(default=0.5, alias="RECAPTCHA_MIN_SCORE")
    # Honored only in development/testing environments (see jobs._verify_recaptcha)
    recaptcha_bypass_in_development: bool = Field(default=False, alias="RECAPTCHA_BYPASS_IN_DEVELOPMENT")

    # Google OAuth
    google_client_id: str | None = Field(default=None, alias="GOOGLE_CLIENT_ID")
    google_client_secret: str | None = Field(default=None, alias="GOOGLE_CLIENT_SECRET")

    # Observability
    sentry_dsn: str | None = Field(default=None, alias="SENTRY_DSN")
    sentry_environment: str | None = Field(default=None, alias="SENTRY_ENVIRONMENT")

    # Resume artifact storage (R14). Durable, S3-compatible object storage for
    # rendered resume PDFs. Backend is Cloudflare R2 in production; falls back to
    # local disk when not configured (dev/test/CI). Values are seeded out-of-band
    # in SSM SecureStrings (never in the repo).
    resume_storage_backend: str = Field(default="local", alias="RESUME_STORAGE_BACKEND")
    resume_s3_bucket: str | None = Field(default=None, alias="RESUME_S3_BUCKET")
    resume_s3_endpoint_url: str | None = Field(default=None, alias="RESUME_S3_ENDPOINT_URL")
    resume_s3_access_key_id: str | None = Field(default=None, alias="RESUME_S3_ACCESS_KEY_ID")
    resume_s3_secret_access_key: str | None = Field(default=None, alias="RESUME_S3_SECRET_ACCESS_KEY")
    resume_s3_region: str = Field(default="auto", alias="RESUME_S3_REGION")

    # Privacy: salt used to hash MSISDN / IP before logging
    ip_salt: str | None = Field(default=None, alias="IP_SALT")

    # Comma-separated IPs/CIDRs whose X-Forwarded-For headers are trusted
    # (defaults to loopback + RFC1918; see app.middleware.rate_limit)
    trusted_proxy_ips: str | None = Field(default=None, alias="TRUSTED_PROXY_IPS")

    # Public base URLs (used for OAuth + email links)
    app_base_url: str | None = Field(default=None, alias="APP_BASE_URL")
    frontend_base_url: str | None = Field(default=None, alias="FRONTEND_BASE_URL")

    # NOTE: M-Pesa and e-Mola fields are intentionally omitted — those adapters
    # are by-design not yet implemented. Add MPESA_* / EMOLA_* fields here when
    # the live integrations land.

    @model_validator(mode="after")
    def apply_environment_defaults(self) -> "Settings":
        environment = (self.environment or "development").strip().lower()
        if self.secret_key in (None, "") and environment in {"development", "dev", "testing", "test"}:
            object.__setattr__(self, "secret_key", "development-only-secret-key")
        return self

    @computed_field(return_type=str)
    @property
    def sync_database_url(self) -> str:
        return self.database_url

    @computed_field(return_type=str)
    @property
    def async_database_url(self) -> str:
        if self.database_url.startswith("postgresql+psycopg2://"):
            return self.database_url.replace("postgresql+psycopg2://", "postgresql+asyncpg://", 1)
        if self.database_url.startswith("postgresql://"):
            return self.database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return self.database_url

    @property
    def migration_database_url(self) -> str:
        return self.alembic_database_url or self.sync_database_url


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
