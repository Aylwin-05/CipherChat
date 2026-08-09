from functools import lru_cache
from pathlib import Path

from pydantic_settings import (
    BaseSettings,
    SettingsConfigDict,
)

# ==========================================================
# Environment
# ==========================================================

BASE_DIR = Path(__file__).resolve().parent.parent.parent

ENV_FILE = BASE_DIR / ".env"


class Settings(BaseSettings):

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ======================================================
    # App
    # ======================================================

    APP_NAME: str = "CipherChat"
    APP_ENV: str = "development"
    DEBUG: bool = True

    HOST: str = "127.0.0.1"
    PORT: int = 8000

    # ======================================================
    # Database
    # ======================================================

    DATABASE_URL: str

    # ======================================================
    # JWT
    # ======================================================

    SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"

    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # ======================================================
    # Cookies (refresh token transport)
    # ======================================================

    COOKIE_SECURE: bool = False
    COOKIE_SAMESITE: str = "lax"
    COOKIE_DOMAIN: str | None = None

    # ======================================================
    # CORS / Hosts
    # ======================================================

    CORS_ORIGINS: str = (
        "http://localhost:5173,http://127.0.0.1:5173"
    )
    ALLOWED_HOSTS: str = "*"

    # ======================================================
    # Redis (rate limiting; falls back to in-memory)
    # ======================================================

    REDIS_URL: str | None = None

    # ======================================================
    # Encryption
    # ======================================================

    MASTER_KEY: str

    # ======================================================
    # SMTP
    # ======================================================

    SMTP_HOST: str
    SMTP_PORT: int

    SMTP_USERNAME: str
    SMTP_PASSWORD: str

    SMTP_FROM_EMAIL: str
    SMTP_FROM_NAME: str


@lru_cache
def get_settings():

    return Settings()


settings = get_settings()