"""API tests for edit, emoji reactions and the forwarded flag."""

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
# Edit (end-to-end encrypted)
# ==========================================================


def test_edit_message_replaces_ciphertext(api_client):
    client = api_client
    token_a, _ = _register(client, EMAIL_A)
    token_b, user_b = _register(client, EMAIL_B)
    conversation_id = _friend_and_conversation(client, token_a, user_b["id"], token_b)
    message = _send(client, conversation_id, token_a, "original-cipher")

    resp = client.put(
        f"/api/v1/messages/{message['id']}/edit",
        json={
            "ciphertext": "edited-cipher",
            "encrypted_key_sender": "k1-new",
            "encrypted_key_receiver": "k2-new",
            "nonce": "n-new",
        },
        headers=_auth(token_a),
    )
    assert resp.status_code == 200, resp.text
    edited = resp.json()
    assert edited["edited"] is True
    assert edited["ciphertext"] == "edited-cipher"
    assert edited["nonce"] == "n-new"

    # Other participant sees the new ciphertext + edited flag
    history = client.get(
        f"/api/v1/messages/{conversation_id}",
        headers=_auth(token_b),
    ).json()
    assert history[0]["edited"] is True
    assert history[0]["ciphertext"] == "edited-cipher"


def test_only_sender_can_edit(api_client):
    client = api_client
    token_a, _ = _register(client, EMAIL_A)
    token_b, user_b = _register(client, EMAIL_B)
    conversation_id = _friend_and_conversation(client, token_a, user_b["id"], token_b)
    message = _send(client, conversation_id, token_a)

    resp = client.put(
        f"/api/v1/messages/{message['id']}/edit",
        json={
            "ciphertext": "hacked-cipher",
            "encrypted_key_sender": "x",
            "encrypted_key_receiver": "y",
            "nonce": "z",
        },
        headers=_auth(token_b),
    )
    assert resp.status_code == 400


def test_cannot_edit_deleted_message(api_client):
    client = api_client
    token_a, _ = _register(client, EMAIL_A)
    token_b, user_b = _register(client, EMAIL_B)
    conversation_id = _friend_and_conversation(client, token_a, user_b["id"], token_b)
    message = _send(client, conversation_id, token_a)

    resp = client.delete(
        f"/api/v1/messages/{message['id']}",
        headers=_auth(token_a),
    )
    assert resp.status_code == 204

    resp = client.put(
        f"/api/v1/messages/{message['id']}/edit",
        json={
            "ciphertext": "after-delete",
            "encrypted_key_sender": "x",
            "encrypted_key_receiver": "y",
            "nonce": "z",
        },
        headers=_auth(token_a),
    )
    assert resp.status_code == 400


# ==========================================================
# Forwarded flag
# ==========================================================


def test_forwarded_flag_serialized(api_client):
    client = api_client
    token_a, _ = _register(client, EMAIL_A)
    token_b, user_b = _register(client, EMAIL_B)
    conversation_id = _friend_and_conversation(client, token_a, user_b["id"], token_b)

    resp = client.post(
        "/api/v1/messages/send",
        json={
            "conversation_id": str(conversation_id),
            "ciphertext": "forwarded-cipher",
            "encrypted_key_sender": "k1",
            "encrypted_key_receiver": "k2",
            "nonce": "n",
            "is_forwarded": True,
        },
        headers=_auth(token_a),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["is_forwarded"] is True

    history = client.get(
        f"/api/v1/messages/{conversation_id}",
        headers=_auth(token_b),
    ).json()
    assert history[0]["is_forwarded"] is True


# ==========================================================
# Reactions
# ==========================================================


def test_reaction_add_and_list(api_client):
    client = api_client
    token_a, _ = _register(client, EMAIL_A)
    token_b, user_b = _register(client, EMAIL_B)
    conversation_id = _friend_and_conversation(client, token_a, user_b["id"], token_b)
    message = _send(client, conversation_id, token_a)

    resp = client.put(
        f"/api/v1/messages/{message['id']}/reaction",
        json={"emoji": "👍"},
        headers=_auth(token_b),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["action"] == "add"
    assert resp.json()["emoji"] == "👍"

    history = client.get(
        f"/api/v1/messages/{conversation_id}",
        headers=_auth(token_a),
    ).json()
    assert len(history[0]["reactions"]) == 1
    assert history[0]["reactions"][0]["user_id"] == str(user_b["id"])
    assert history[0]["reactions"][0]["emoji"] == "👍"


def test_reaction_toggle_removes(api_client):
    client = api_client
    token_a, _ = _register(client, EMAIL_A)
    token_b, user_b = _register(client, EMAIL_B)
    conversation_id = _friend_and_conversation(client, token_a, user_b["id"], token_b)
    message = _send(client, conversation_id, token_a)

    client.put(
        f"/api/v1/messages/{message['id']}/reaction",
        json={"emoji": "❤️"},
        headers=_auth(token_b),
    )
    resp = client.put(
        f"/api/v1/messages/{message['id']}/reaction",
        json={"emoji": "❤️"},
        headers=_auth(token_b),
    )
    assert resp.status_code == 200
    assert resp.json()["action"] == "remove"

    history = client.get(
        f"/api/v1/messages/{conversation_id}",
        headers=_auth(token_a),
    ).json()
    assert history[0]["reactions"] == []


def test_reaction_replaces_previous(api_client):
    client = api_client
    token_a, _ = _register(client, EMAIL_A)
    token_b, user_b = _register(client, EMAIL_B)
    conversation_id = _friend_and_conversation(client, token_a, user_b["id"], token_b)
    message = _send(client, conversation_id, token_a)

    client.put(
        f"/api/v1/messages/{message['id']}/reaction",
        json={"emoji": "👍"},
        headers=_auth(token_b),
    )
    resp = client.put(
        f"/api/v1/messages/{message['id']}/reaction",
        json={"emoji": "😂"},
        headers=_auth(token_b),
    )
    assert resp.json()["action"] == "add"

    history = client.get(
        f"/api/v1/messages/{conversation_id}",
        headers=_auth(token_a),
    ).json()
    assert len(history[0]["reactions"]) == 1
    assert history[0]["reactions"][0]["emoji"] == "😂"


def test_reaction_requires_participant(api_client):
    client = api_client
    token_a, _ = _register(client, EMAIL_A)
    token_b, user_b = _register(client, EMAIL_B)
    token_c, _ = _register(client, EMAIL_C)
    conversation_id = _friend_and_conversation(client, token_a, user_b["id"], token_b)
    message = _send(client, conversation_id, token_a)

    resp = client.put(
        f"/api/v1/messages/{message['id']}/reaction",
        json={"emoji": "👍"},
        headers=_auth(token_c),
    )
    assert resp.status_code == 400