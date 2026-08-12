"""API tests for conversation pin / archive / mute settings."""

import asyncio
import time
from datetime import datetime, timedelta, timezone

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
from app.database.base import Base
from app.database.session import get_db
from app.main import app as app_instance

EMAIL_A = "alice@example.com"
EMAIL_B = "bob@example.com"
EMAIL_C = "mallory@example.com"


class EmailRecorder:
    sent: list[dict] = []

    @classmethod
    async def send_otp_email(cls, recipient_email: str, otp: str, **kwargs):
        cls.sent.append({"email": recipient_email, "otp": otp})


@pytest.fixture
def api_client(monkeypatch):
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


def _friend_and_conversation(client, token_a, bob_id, token_b):
    resp = client.post(
        "/api/v1/friends/request",
        json={"receiver_id": str(bob_id)},
        headers=_auth(token_a),
    )
    assert resp.status_code == 200, resp.text

    pending = client.get(
        "/api/v1/friends/pending",
        headers=_auth(token_b),
    ).json()
    friendship_id = pending[0]["id"]

    resp = client.post(
        "/api/v1/friends/accept",
        json={"friendship_id": str(friendship_id)},
        headers=_auth(token_b),
    )
    assert resp.status_code == 200, resp.text

    resp = client.post(
        "/api/v1/conversations/private",
        json={"user_id": str(bob_id)},
        headers=_auth(token_a),
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


def _second_conversation(client, token_a, mallory_id, token_b):
    resp = client.post(
        "/api/v1/friends/request",
        json={"receiver_id": str(mallory_id)},
        headers=_auth(token_a),
    )
    assert resp.status_code == 200, resp.text

    pending = client.get(
        "/api/v1/friends/pending",
        headers=_auth(token_b),
    ).json()
    friendship_id = pending[0]["id"]

    resp = client.post(
        "/api/v1/friends/accept",
        json={"friendship_id": str(friendship_id)},
        headers=_auth(token_b),
    )
    assert resp.status_code == 200, resp.text

    resp = client.post(
        "/api/v1/conversations/private",
        json={"user_id": str(mallory_id)},
        headers=_auth(token_a),
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


def _send(client, conversation_id, token, content="payload"):
    resp = client.post(
        "/api/v1/messages/send",
        json={
            "conversation_id": str(conversation_id),
            "ciphertext": content,
            "encrypted_key_sender": "k1",
            "encrypted_key_receiver": "k2",
            "nonce": "n",
        },
        headers=_auth(token),
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


# ==========================================================
# Pin
# ==========================================================


def test_pin_and_unpin_conversation(api_client):
    client = api_client
    token_a, _ = _register(client, EMAIL_A)
    token_b, user_b = _register(client, EMAIL_B)
    token_c, user_c = _register(client, EMAIL_C)

    conv_b = _friend_and_conversation(client, token_a, user_b["id"], token_b)

    # SQLite timestamps have 1-second resolution; make the newer
    # conversation's timestamp strictly later than the first one.
    time.sleep(1.1)

    conv_c = _second_conversation(client, token_a, user_c["id"], token_c)
    _send(client, conv_c, token_a, "newest")

    # Pin the older conversation
    resp = client.patch(
        f"/api/v1/conversations/{conv_b}",
        json={"is_pinned": True},
        headers=_auth(token_a),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["is_pinned"] is True

    # Pinned conversation now sorts above the newer one
    conversations = client.get(
        "/api/v1/conversations/",
        headers=_auth(token_a),
    ).json()
    assert conversations[0]["id"] == conv_b
    assert conversations[0]["is_pinned"] is True

    # Unpin
    resp = client.patch(
        f"/api/v1/conversations/{conv_b}",
        json={"is_pinned": False},
        headers=_auth(token_a),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["is_pinned"] is False

    conversations = client.get(
        "/api/v1/conversations/",
        headers=_auth(token_a),
    ).json()
    assert conversations[0]["id"] == conv_c


def test_pin_settings_are_per_user(api_client):
    client = api_client
    token_a, _ = _register(client, EMAIL_A)
    token_b, user_b = _register(client, EMAIL_B)

    conv = _friend_and_conversation(client, token_a, user_b["id"], token_b)

    resp = client.patch(
        f"/api/v1/conversations/{conv}",
        json={"is_pinned": True},
        headers=_auth(token_a),
    )
    assert resp.status_code == 200

    # Bob does NOT see the pin
    conversations = client.get(
        "/api/v1/conversations/",
        headers=_auth(token_b),
    ).json()
    assert conversations[0]["is_pinned"] is False


# ==========================================================
# Archive
# ==========================================================


def test_archive_flags_conversation(api_client):
    client = api_client
    token_a, _ = _register(client, EMAIL_A)
    token_b, user_b = _register(client, EMAIL_B)

    conv = _friend_and_conversation(client, token_a, user_b["id"], token_b)

    resp = client.patch(
        f"/api/v1/conversations/{conv}",
        json={"is_archived": True},
        headers=_auth(token_a),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["is_archived"] is True

    conversations = client.get(
        "/api/v1/conversations/",
        headers=_auth(token_a),
    ).json()
    assert conversations[0]["is_archived"] is True


# ==========================================================
# Mute
# ==========================================================


def test_mute_until_future_is_muted(api_client):
    client = api_client
    token_a, _ = _register(client, EMAIL_A)
    token_b, user_b = _register(client, EMAIL_B)

    conv = _friend_and_conversation(client, token_a, user_b["id"], token_b)

    future = datetime.now(timezone.utc) + timedelta(hours=8)
    resp = client.patch(
        f"/api/v1/conversations/{conv}",
        json={"muted_until": future.isoformat()},
        headers=_auth(token_a),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["muted"] is True


def test_mute_until_past_is_not_muted(api_client):
    client = api_client
    token_a, _ = _register(client, EMAIL_A)
    token_b, user_b = _register(client, EMAIL_B)

    conv = _friend_and_conversation(client, token_a, user_b["id"], token_b)

    past = datetime.now(timezone.utc) - timedelta(hours=8)
    resp = client.patch(
        f"/api/v1/conversations/{conv}",
        json={"muted_until": past.isoformat()},
        headers=_auth(token_a),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["muted"] is False


def test_unmute_clears_mute(api_client):
    client = api_client
    token_a, _ = _register(client, EMAIL_A)
    token_b, user_b = _register(client, EMAIL_B)

    conv = _friend_and_conversation(client, token_a, user_b["id"], token_b)

    future = datetime.now(timezone.utc) + timedelta(hours=8)
    client.patch(
        f"/api/v1/conversations/{conv}",
        json={"muted_until": future.isoformat()},
        headers=_auth(token_a),
    )

    resp = client.patch(
        f"/api/v1/conversations/{conv}",
        json={"muted_until": None},
        headers=_auth(token_a),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["muted"] is False


# ==========================================================
# Permissions
# ==========================================================


def test_non_participant_cannot_update_settings(api_client):
    client = api_client
    token_a, _ = _register(client, EMAIL_A)
    token_b, user_b = _register(client, EMAIL_B)
    token_c, _ = _register(client, EMAIL_C)

    conv = _friend_and_conversation(client, token_a, user_b["id"], token_b)

    resp = client.patch(
        f"/api/v1/conversations/{conv}",
        json={"is_pinned": True},
        headers=_auth(token_c),
    )
    assert resp.status_code == 403, resp.text


def test_invalid_conversation_id_rejected(api_client):
    client = api_client
    token_a, _ = _register(client, EMAIL_A)

    resp = client.patch(
        "/api/v1/conversations/not-a-uuid",
        json={"is_pinned": True},
        headers=_auth(token_a),
    )
    assert resp.status_code == 400, resp.text