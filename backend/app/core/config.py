"""
GramCare – Application configuration
All values are read from environment variables / .env file.
"""

from functools import lru_cache
from typing import List

from pydantic import AnyHttpUrl, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── App ────────────────────────────────────────────────────────────────
    APP_NAME: str = "GramCare"
    APP_ENV: str = "development"
    DEBUG: bool = True
    # Auto-create tables on startup via SQLAlchemy metadata instead of
    # requiring `alembic upgrade head` first. Handy for a from-scratch local
    # Postgres; skip it (the default) once migrations are the source of
    # truth — it's a slow no-op checkfirst round trip per table on every
    # boot against a remote DB, and alembic should own schema changes.
    AUTO_CREATE_TABLES: bool = False
    SECRET_KEY: str = "change-me"
    ALLOWED_ORIGINS: str = "http://localhost:3000"

    @property
    def cors_origins(self) -> List[str]:
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",")]

    # ── Database ───────────────────────────────────────────────────────────
    DATABASE_URL: str = "postgresql+asyncpg://gramcare_user:gramcare_password@localhost:5432/gramcare"
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "gramcare"
    POSTGRES_USER: str = "gramcare_user"
    POSTGRES_PASSWORD: str = "gramcare_password"

    # ── Redis ──────────────────────────────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_SESSION_DB: int = 1
    REDIS_CELERY_DB: int = 2

    # ── MinIO / S3 ─────────────────────────────────────────────────────────
    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin"
    MINIO_BUCKET_MEDIA: str = "gramcare-media"
    MINIO_BUCKET_DOCUMENTS: str = "gramcare-docs"
    MINIO_USE_SSL: bool = False

    # ── JWT ────────────────────────────────────────────────────────────────
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    OTP_EXPIRE_MINUTES: int = 10
    OTP_LENGTH: int = 6

    # ── OTP ────────────────────────────────────────────────────────────────
    # Cost-cutting: no paid SMS gateway. OTP is logged to the server console
    # in dev; wire in a free/self-hosted SMS/WhatsApp gateway for prod later.
    CONSOLE_OTP: bool = True

    # ── WebRTC (peer-to-peer, no SFU) ──────────────────────────────────────
    # STUN is free (public Google STUN by default). TURN only relays media
    # when a direct P2P path fails behind strict NAT — self-host coturn
    # (open source, see docker-compose.yml) instead of a paid TURN SaaS.
    STUN_URLS: str = "stun:stun.l.google.com:19302"
    TURN_URL: str = "turn:localhost:3478"
    TURN_USERNAME: str = "gramcare"
    TURN_CREDENTIAL: str = "gramcarepass"
    TURN_ENABLED: bool = False  # flip on once coturn is deployed

    @property
    def stun_urls(self) -> List[str]:
        return [u.strip() for u in self.STUN_URLS.split(",") if u.strip()]

    # ── Sync ───────────────────────────────────────────────────────────────
    SYNC_MAX_BATCH_SIZE: int = 100
    SYNC_CHECKPOINT_INTERVAL_SECONDS: int = 30

    # ── Rate limiting ──────────────────────────────────────────────────────
    RATE_LIMIT_OTP_PER_HOUR: int = 5
    RATE_LIMIT_API_PER_MINUTE: int = 120


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
