"""API tests for disappearing messages (conversation timer + expiry purge)."""

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
import app.websocket.connection_manager as conn_mgr
from app.core.rate_limit import reset_limiter
from app.database.base import Base
from app.database.session import get_db
from app.main import app as app_instance

EMAIL_A = "alice@example.com"
EMAIL_B = "bob@example.com"


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
# Timer setting
# ==========================================================


def test_default_timer_is_off(api_client):
    client = api_client
    token_a, _ = _register(client, EMAIL_A)
    token_b, user_b = _register(client, EMAIL_B)

    conv = _friend_and_conversation(client, token_a, user_b["id"], token_b)

    conversations = client.get(
        "/api/v1/conversations/",
        headers=_auth(token_a),
    ).json()
    assert conversations[0]["disappear_after_seconds"] is None


def test_set_timer_shared_by_both_participants(api_client):
    client = api_client
    token_a, _ = _register(client, EMAIL_A)
    token_b, user_b = _register(client, EMAIL_B)

    conv = _friend_and_conversation(client, token_a, user_b["id"], token_b)

    resp = client.patch(
        f"/api/v1/conversations/{conv}",
        json={"disappear_after_seconds": 24 * 60 * 60},
        headers=_auth(token_a),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["disappear_after_seconds"] == 86400

    # Bob sees the same shared setting
    conversations = client.get(
        "/api/v1/conversations/",
        headers=_auth(token_b),
    ).json()
    assert conversations[0]["disappear_after_seconds"] == 86400

    # Alice sees it too
    conversations = client.get(
        "/api/v1/conversations/",
        headers=_auth(token_a),
    ).json()
    assert conversations[0]["disappear_after_seconds"] == 86400


def test_disable_timer(api_client):
    client = api_client
    token_a, _ = _register(client, EMAIL_A)
    token_b, user_b = _register(client, EMAIL_B)

    conv = _friend_and_conversation(client, token_a, user_b["id"], token_b)

    client.patch(
        f"/api/v1/conversations/{conv}",
        json={"disappear_after_seconds": 3600},
        headers=_auth(token_a),
    )

    resp = client.patch(
        f"/api/v1/conversations/{conv}",
        json={"disappear_after_seconds": None},
        headers=_auth(token_a),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["disappear_after_seconds"] is None


# ==========================================================
# Messages get an expiry timestamp
# ==========================================================


def test_messages_receive_expires_at_when_timer_on(api_client):
    client = api_client
    token_a, _ = _register(client, EMAIL_A)
    token_b, user_b = _register(client, EMAIL_B)

    conv = _friend_and_conversation(client, token_a, user_b["id"], token_b)

    # Before the timer: no expiry
    message = _send(client, conv, token_a, "persistent-msg")
    assert message["expires_at"] is None

    client.patch(
        f"/api/v1/conversations/{conv}",
        json={"disappear_after_seconds": 3600},
        headers=_auth(token_a),
    )

    message = _send(client, conv, token_a, "vanishing-msg")
    assert message["expires_at"] is not None

    # History shows the expiry to both participants
    for token in (token_a, token_b):
        history = client.get(
            f"/api/v1/messages/{conv}",
            headers=_auth(token),
        ).json()
        assert len(history) == 2
        assert history[0]["expires_at"] is None
        assert history[1]["expires_at"] is not None


# ==========================================================
# Purge
# ==========================================================


def test_expired_message_is_purged_from_history(api_client):
    client = api_client
    token_a, _ = _register(client, EMAIL_A)
    token_b, user_b = _register(client, EMAIL_B)

    conv = _friend_and_conversation(client, token_a, user_b["id"], token_b)

    # Two messages: one persistent, one that expires in 1 second
    _send(client, conv, token_a, "persistent-msg")

    client.patch(
        f"/api/v1/conversations/{conv}",
        json={"disappear_after_seconds": 1},
        headers=_auth(token_a),
    )

    message = _send(client, conv, token_a, "vanishing-msg")

    import time as _time
    _time.sleep(1.2)

    history = client.get(
        f"/api/v1/messages/{conv}",
        headers=_auth(token_b),
    ).json()

    assert len(history) == 1
    assert history[0]["ciphertext"] == "persistent-msg"
    assert history[0]["id"] != message["id"]


def test_expired_message_not_in_conversation_preview(api_client):
    client = api_client
    token_a, _ = _register(client, EMAIL_A)
    token_b, user_b = _register(client, EMAIL_B)

    conv = _friend_and_conversation(client, token_a, user_b["id"], token_b)

    client.patch(
        f"/api/v1/conversations/{conv}",
        json={"disappear_after_seconds": 1},
        headers=_auth(token_a),
    )

    _send(client, conv, token_a, "vanishing-last-msg")

    import time as _time
    _time.sleep(1.2)

    conversations = client.get(
        "/api/v1/conversations/",
        headers=_auth(token_a),
    ).json()

    # The preview must not reference the vanished message
    item = next(
        c for c in conversations if c["id"] == conv
    )
    assert item["last_message"] is None
    assert item["unread_count"] == 0


def test_expired_message_cannot_be_replied_to(api_client):
    client = api_client
    token_a, _ = _register(client, EMAIL_A)
    token_b, user_b = _register(client, EMAIL_B)

    conv = _friend_and_conversation(client, token_a, user_b["id"], token_b)

    client.patch(
        f"/api/v1/conversations/{conv}",
        json={"disappear_after_seconds": 1},
        headers=_auth(token_a),
    )

    message = _send(client, conv, token_a, "vanishing-msg")

    import time as _time
    _time.sleep(1.2)

    resp = client.post(
        "/api/v1/messages/send",
        json={
            "conversation_id": str(conv),
            "ciphertext": "reply",
            "encrypted_key_sender": "k",
            "encrypted_key_receiver": "k",
            "nonce": "n",
            "reply_to_id": str(message["id"]),
        },
        headers=_auth(token_b),
    )
    assert resp.status_code == 400, resp.text