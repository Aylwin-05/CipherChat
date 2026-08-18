"""Tests for the "I lost my recovery code" re-issue flow."""

import asyncio
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

import app.services.email_service as email_module
import app.websocket.connection_manager as conn_mgr
from app.core.rate_limit import reset_limiter
from app.crypto.signal.primitives import (
    b64encode,
    ed25519_private_to_bytes,
    ed25519_public_to_bytes,
    ed25519_sign,
    generate_ed25519_keypair,
    generate_x25519_keypair,
    x25519_private_to_bytes,
    x25519_public_to_bytes,
)
from app.crypto.signal.x3dh import derive_x25519_from_ed25519
from app.database.base import Base
from app.database.session import get_db
from app.main import app as app_instance
from app.services.recovery_service import (
    unlock_sync_secret,
    recovery_token_store,
)

EMAIL_A = "alice@example.com"


class EmailRecorder:
    sent: list[dict] = []

    @classmethod
    async def send_otp_email(cls, recipient_email: str, otp: str, **kwargs):
        cls.sent.append({"email": recipient_email, "otp": otp})

    @classmethod
    async def send_recovery_code_email(cls, recipient_email: str, code: str, **kwargs):
        cls.sent.append({"email": recipient_email, "code": code})

    @classmethod
    async def send_recovery_link_email(cls, recipient_email: str, link_url: str, **kwargs):
        cls.sent.append({"email": recipient_email, "link": link_url})


@pytest.fixture
def api_client(monkeypatch):
    monkeypatch.setattr(
        email_module.EmailService,
        "send_otp_email",
        EmailRecorder.send_otp_email,
    )
    monkeypatch.setattr(
        email_module.EmailService,
        "send_recovery_code_email",
        EmailRecorder.send_recovery_code_email,
    )
    monkeypatch.setattr(
        email_module.EmailService,
        "send_recovery_link_email",
        EmailRecorder.send_recovery_link_email,
    )
    EmailRecorder.sent = []
    recovery_token_store.clear()
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
    monkeypatch.setattr(
        conn_mgr,
        "AsyncSessionLocal",
        TestingSessionLocal,
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


def _register(client, email):
    client.post("/api/v1/auth/send-otp", json={"email": email})
    otp = EmailRecorder.sent[-1]["otp"]
    resp = client.post(
        "/api/v1/auth/verify-otp",
        json={"email": email, "otp": otp},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    return data["access_token"], data["user"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def make_key_material() -> dict:
    identity_priv, identity_pub = generate_ed25519_keypair()
    identity_x25519 = derive_x25519_from_ed25519(identity_priv)
    identity_x25519_pub = identity_x25519.public_key()

    spk_priv, spk_pub = generate_x25519_keypair()
    spk_pub_bytes = x25519_public_to_bytes(spk_pub)
    signature = ed25519_sign(identity_priv, spk_pub_bytes)

    opks = []
    for kid in range(1, 3):
        p, q = generate_x25519_keypair()
        opks.append({
            "key_id": kid,
            "public_key": b64encode(x25519_public_to_bytes(q)),
            "private_key_encrypted": b64encode(
                b64encode(x25519_private_to_bytes(p)).encode()
            ),
        })

    return {
        "identity_key_public": b64encode(ed25519_public_to_bytes(identity_pub)),
        "identity_key_x25519": b64encode(x25519_public_to_bytes(identity_x25519_pub)),
        "identity_key_private_encrypted": b64encode(
            b64encode(ed25519_private_to_bytes(identity_priv)).encode()
        ),
        "signed_prekey_public": b64encode(spk_pub_bytes),
        "signed_prekey_private_encrypted": b64encode(
            b64encode(x25519_private_to_bytes(spk_priv)).encode()
        ),
        "signed_prekey_id": 1,
        "signed_prekey_signature": b64encode(signature),
        "one_time_prekeys": opks,
    }


def _register_device(client, token, device_id):
    resp = client.post(
        "/api/v1/devices/register",
        json={
            "device_id": device_id,
            "platform": "web",
            "device_name": "Test Browser",
            **make_key_material(),
        },
        headers=_auth(token),
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _create_account_with_secret(client, email=EMAIL_A):
    """Register + register a device: account gets a recovery code."""
    token, user = _register(client, email)
    device = _register_device(client, token, f"dev-{uuid.uuid4().hex[:8]}")
    assert device["recovery_code"], "first registration mints a code"
    return token, user, device


def _link_from_emails():
    link = [
        e for e in EmailRecorder.sent
        if e.get("link")
    ][-1]["link"]
    return link.split("token=")[1]


def _send_otp_for(client, email):
    client.post("/api/v1/auth/send-otp", json={"email": email})
    return EmailRecorder.sent[-1]["otp"]


# ==========================================================
# Request endpoint
# ==========================================================


def test_recovery_request_requires_auth(api_client):
    resp = api_client.post("/api/v1/recovery/request", json={})
    assert resp.status_code == 401


def test_recovery_request_rewraps_same_secret(api_client):
    token, _, device = _create_account_with_secret(api_client)

    secret = unlock_sync_secret(
        device["recovery_code"].replace("-", ""),
        device["recovery_salt"],
        device["recovery_wrapped_key"],
    )
    assert secret, "the original code unlocks the secret"

    resp = api_client.post(
        "/api/v1/recovery/request",
        json={"secret_b64": secret},
        headers=_auth(token),
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["mode"] == "same_secret"
    assert data["remaining"] == 2
    assert data["retry_after"] <= 600
    assert "link" in [e for e in EmailRecorder.sent if e.get("link")][-1]

    # The old code no longer matches what the server now serves
    # (the salt was replaced); a client that cached the old
    # material would still decrypt it, but that material is gone.
    current = api_client.get(
        "/api/v1/recovery/unlock",
        headers=_auth(token),
    ).json()
    assert unlock_sync_secret(
        device["recovery_code"].replace("-", ""),
        current["salt"],
        current["wrapped_key"],
    ) is None

    # Complete the flow: OTP -> new code -> SAME secret back.
    otp = _send_otp_for(api_client, EMAIL_A)
    token_val = _link_from_emails()
    resp = api_client.post(
        "/api/v1/recovery/verify",
        json={"token": token_val, "email": EMAIL_A, "otp": otp},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["code_display"] != device["recovery_code"]

    recovered = unlock_sync_secret(
        data["code"].replace("-", ""),
        data["salt"],
        data["wrapped_key"],
    )
    assert recovered == secret, "the SAME secret is re-wrapped"


def test_recovery_request_mints_fresh_key_without_secret(api_client):
    token, _, device = _create_account_with_secret(api_client)
    old_secret = unlock_sync_secret(
        device["recovery_code"].replace("-", ""),
        device["recovery_salt"],
        device["recovery_wrapped_key"],
    )

    resp = api_client.post(
        "/api/v1/recovery/request",
        json={},
        headers=_auth(token),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["mode"] == "new_secret"

    otp = _send_otp_for(api_client, EMAIL_A)
    resp = api_client.post(
        "/api/v1/recovery/verify",
        json={"token": _link_from_emails(), "email": EMAIL_A, "otp": otp},
    )
    data = resp.json()
    new_secret = unlock_sync_secret(
        data["code"].replace("-", ""),
        data["salt"],
        data["wrapped_key"],
    )
    assert new_secret is not None
    assert new_secret != old_secret, "fresh mint -> brand-new secret"


def test_recovery_request_rejects_bad_secret(api_client):
    token, _, _ = _create_account_with_secret(api_client)
    resp = api_client.post(
        "/api/v1/recovery/request",
        json={"secret_b64": "bm90LWEtc2VjcmV0IQ=="},
        headers=_auth(token),
    )
    assert resp.status_code == 400


def test_recovery_request_rate_limited_per_email(api_client):
    token, _, _ = _create_account_with_secret(api_client)

    for _ in range(3):
        resp = api_client.post(
            "/api/v1/recovery/request",
            json={},
            headers=_auth(token),
        )
        assert resp.status_code == 200, resp.text

    resp = api_client.post(
        "/api/v1/recovery/request",
        json={},
        headers=_auth(token),
    )
    assert resp.status_code == 429
    assert "Retry-After" in resp.headers


def test_recovery_re_request_revokes_previous_link(api_client):
    token, _, _ = _create_account_with_secret(api_client)

    api_client.post(
        "/api/v1/recovery/request",
        json={},
        headers=_auth(token),
    )
    first_token = _link_from_emails()

    api_client.post(
        "/api/v1/recovery/request",
        json={},
        headers=_auth(token),
    )

    otp = _send_otp_for(api_client, EMAIL_A)
    resp = api_client.post(
        "/api/v1/recovery/verify",
        json={"token": first_token, "email": EMAIL_A, "otp": otp},
    )
    assert resp.status_code == 404, "superseded link is dead"


# ==========================================================
# Verify endpoint
# ==========================================================


def test_recovery_verify_rejects_bad_token(api_client):
    token, _, _ = _create_account_with_secret(api_client)
    api_client.post(
        "/api/v1/recovery/request",
        json={},
        headers=_auth(token),
    )
    resp = api_client.post(
        "/api/v1/recovery/verify",
        json={"token": "garbage-token", "email": EMAIL_A, "otp": "123456"},
    )
    assert resp.status_code == 404


def test_recovery_verify_rejects_wrong_email(api_client):
    token, _, _ = _create_account_with_secret(api_client)
    api_client.post(
        "/api/v1/recovery/request",
        json={},
        headers=_auth(token),
    )
    otp = _send_otp_for(api_client, EMAIL_A)
    resp = api_client.post(
        "/api/v1/recovery/verify",
        json={
            "token": _link_from_emails(),
            "email": "mallory@example.com",
            "otp": otp,
        },
    )
    assert resp.status_code == 403


def test_recovery_verify_rejects_wrong_otp(api_client):
    token, _, _ = _create_account_with_secret(api_client)
    api_client.post(
        "/api/v1/recovery/request",
        json={},
        headers=_auth(token),
    )
    resp = api_client.post(
        "/api/v1/recovery/verify",
        json={
            "token": _link_from_emails(),
            "email": EMAIL_A,
            "otp": "000000",
        },
    )
    assert resp.status_code == 400


def test_recovery_verify_consumes_otp_once(api_client):
    token, _, _ = _create_account_with_secret(api_client)
    api_client.post(
        "/api/v1/recovery/request",
        json={},
        headers=_auth(token),
    )
    otp = _send_otp_for(api_client, EMAIL_A)

    resp = api_client.post(
        "/api/v1/recovery/verify",
        json={"token": _link_from_emails(), "email": EMAIL_A, "otp": otp},
    )
    assert resp.status_code == 200, resp.text

    resp = api_client.post(
        "/api/v1/recovery/verify",
        json={"token": _link_from_emails(), "email": EMAIL_A, "otp": otp},
    )
    assert resp.status_code == 404, "token consumed on success"