"""API integration tests for OTP auth, refresh rotation and
rate limiting."""

import asyncio

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

import app.services.email_service as email_module
from app.core.rate_limit import reset_limiter
from app.database.base import Base
from app.database.session import get_db
from app.main import app as app_instance

EMAIL = "alice@example.com"


class EmailRecorder:
    """Captures OTPs instead of hitting SMTP."""

    sent: list[dict] = []

    @classmethod
    async def send_otp_email(cls, recipient_email: str, otp: str, **kwargs):
        cls.sent.append({"email": recipient_email, "otp": otp})


@pytest.fixture
def auth_client(monkeypatch):
    """TestClient against an in-memory DB, SMTP replaced by a recorder."""

    monkeypatch.setattr(
        email_module.EmailService,
        "send_otp_email",
        EmailRecorder.send_otp_email,
    )
    EmailRecorder.sent = []
    reset_limiter()

    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async def override_get_db():
        async with TestingSessionLocal() as session:
            yield session

    async def setup():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(setup())

    app_instance.dependency_overrides[get_db] = override_get_db

    with TestClient(app_instance) as client:
        yield client

    app_instance.dependency_overrides.clear()


# ==========================================================
# Helpers
# ==========================================================


def _request_otp(client, email=EMAIL):
    resp = client.post("/api/v1/auth/send-otp", json={"email": email})
    assert resp.status_code == 200, resp.text
    return EmailRecorder.sent[-1]["otp"]


def _verify_otp(client, email=EMAIL, otp="123456"):
    return client.post(
        "/api/v1/auth/verify-otp",
        json={"email": email, "otp": otp},
    )


# ==========================================================
# OTP lifecycle
# ==========================================================


def test_send_and_verify_otp(auth_client):
    client = auth_client
    otp = _request_otp(client)

    resp = _verify_otp(client, otp=otp)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["user"]["email"] == EMAIL

    # Refresh token arrives in an HttpOnly cookie too
    set_cookie = resp.headers.get("set-cookie", "")
    assert "cc_refresh=" in set_cookie
    assert "HttpOnly" in set_cookie


def test_verify_wrong_otp_exhausts_attempts(auth_client):
    _request_otp(auth_client)
    for _ in range(5):
        resp = _verify_otp(auth_client, otp="000000")
        assert resp.status_code == 400

    resp = _verify_otp(auth_client, otp="000000")
    assert resp.status_code == 400


def test_verify_used_otp_rejected(auth_client):
    otp = _request_otp(auth_client)
    assert _verify_otp(auth_client, otp=otp).status_code == 200
    assert _verify_otp(auth_client, otp=otp).status_code == 400


# ================================================================
# Refresh rotation + reuse detection + logout
# ================================================================


def test_refresh_rotates_token(auth_client):
    client = auth_client
    otp = _request_otp(client)
    refresh_token = _verify_otp(client, otp=otp).json()["refresh_token"]

    resp = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert resp.status_code == 200, resp.text
    new_refresh = resp.json()["refresh_token"]
    assert new_refresh != refresh_token

    # Replay the rotated-away token (no cookie to hide behind)
    client.cookies.clear()
    resp = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert resp.status_code == 401


def test_reuse_after_rotation_revokes_family(auth_client):
    client = auth_client
    otp = _request_otp(client)
    refresh_token = _verify_otp(client, otp=otp).json()["refresh_token"]

    resp = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    new_refresh = resp.json()["refresh_token"]

    # Replay the old token -> whole family revoked
    client.cookies.clear()
    client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )

    resp = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": new_refresh},
    )
    assert resp.status_code == 401


def test_logout_revokes_family(auth_client):
    client = auth_client
    otp = _request_otp(client)
    refresh = _verify_otp(client, otp=otp).json()["refresh_token"]

    resp = client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": refresh},
    )
    assert resp.status_code == 200

    resp = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh},
    )
    assert resp.status_code == 401


def test_refresh_without_token_401(auth_client):
    resp = auth_client.post("/api/v1/auth/refresh", json={})
    assert resp.status_code == 401


# ================================================================
# Rate limiting
# ================================================================


def test_send_otp_rate_limited_per_email(auth_client):
    client = auth_client
    for _ in range(3):
        resp = client.post(
            "/api/v1/auth/send-otp",
            json={"email": "bob@example.com"},
        )
        assert resp.status_code == 200, resp.text

    resp = client.post(
        "/api/v1/auth/send-otp",
        json={"email": "bob@example.com"},
    )
    assert resp.status_code == 429