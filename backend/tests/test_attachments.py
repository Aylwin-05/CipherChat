"""API tests for encrypted message sending and attachment
authorization (upload/download from a `.bin` encrypted file)."""

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


def _register(client, email):
    client.post("/api/v1/auth/send-otp", json={"email": email})
    otp = EmailRecorder.sent[-1]["otp"]
    resp = client.post(
        "/api/v1/auth/verify-otp",
        json={"email": email, "otp": otp},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    return (
        data["access_token"],
        data["user"],
    )


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _friend_and_conversation(client, token_a, bob_id, token_b):
    """Alice sends a friend request; Bob accepts; both get a conversation."""

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


# ==========================================================
# Messages
# ==========================================================


def test_send_encrypted_message_and_history(api_client):
    client = api_client
    token_a, user_a = _register(client, EMAIL_A)
    token_b, user_b = _register(client, EMAIL_B)
    conversation_id = _friend_and_conversation(client, token_a, user_b["id"], token_b)

    payload = {
        "conversation_id": str(conversation_id),
        "ciphertext": "cipher-blob",
        "encrypted_key_sender": "key-s",
        "encrypted_key_receiver": "key-r",
        "nonce": "deadbeef",
        "crypto_version": 2,
        "message_type": "text",
        "reply_to_id": None,
    }

    resp = client.post(
        "/api/v1/messages/send",
        json=payload,
        headers=_auth(token_a),
    )
    assert resp.status_code == 200, resp.text
    message = resp.json()
    assert message["ciphertext"] == "cipher-blob"

    # Recipient can read history
    resp = client.get(
        f"/api/v1/messages/{conversation_id}",
        headers=_auth(token_b),
    )
    assert resp.status_code == 200, resp.text
    history = resp.json()
    assert len(history) == 1
    assert history[0]["sender_id"] == str(user_a["id"])
    assert history[0]["is_read"] is False

    # Unread surfaced through the conversation list
    conversations = client.get(
        "/api/v1/conversations/",
        headers=_auth(token_b),
    ).json()
    conv_b = next(
        c for c in conversations if c["id"] == str(conversation_id)
    )
    assert conv_b["unread_count"] == 1


def test_non_participant_cannot_read_history(api_client):
    client = api_client
    token_a, _ = _register(client, EMAIL_A)
    token_b, user_b = _register(client, EMAIL_B)
    token_c, _ = _register(client, EMAIL_C)
    conversation_id = _friend_and_conversation(client, token_a, user_b["id"], token_b)

    resp = client.get(
        f"/api/v1/messages/{conversation_id}",
        headers=_auth(token_c),
    )
    assert resp.status_code == 400, resp.text


# ==========================================================
# Attachments (encrypted `.bin`)
# ==========================================================


def _send_message(client, conversation_id, token):
    return client.post(
        "/api/v1/messages/send",
        json={
            "conversation_id": str(conversation_id),
            "ciphertext": "payload",
            "encrypted_key_sender": "k1",
            "encrypted_key_receiver": "k2",
            "nonce": "n",
            "crypto_version": 2,
            "message_type": "text",
            "reply_to_id": None,
        },
        headers=_auth(token),
    ).json()


def test_upload_download_encrypted_bin(api_client):
    client = api_client
    token_a, _ = _register(client, EMAIL_A)
    token_b, user_b = _register(client, EMAIL_B)
    conversation_id = _friend_and_conversation(client, token_a, user_b["id"], token_b)
    message = _send_message(client, conversation_id, token_a)
    message_id = message["id"]

    # Upload a `.bin` encrypted file (what the client actually sends)
    resp = client.post(
        f"/api/v1/attachments/upload/{message_id}",
        headers=_auth(token_a),
        files={
            "file": (
                "photo.jpg.bin",
                b"\x00" * 1024,
                "application/octet-stream",
            )
        },
    )
    assert resp.status_code == 200, resp.text
    attachment = resp.json()["attachment"]
    assert attachment["attachment_type"] == "encrypted"
    assert attachment["size"] == 1024

    # Recipient (participant, not sender) can download
    resp = client.get(
        f"/api/v1/attachments/{attachment['id']}",
        headers=_auth(token_b),
    )
    assert resp.status_code == 200, resp.text
    assert resp.content == b"\x00" * 1024

    # The sender can download too
    resp = client.get(
        f"/api/v1/attachments/{attachment['id']}",
        headers=_auth(token_a),
    )
    assert resp.status_code == 200


def test_attachment_rejected_for_non_participant(api_client):
    client = api_client
    token_a, _ = _register(client, EMAIL_A)
    token_b, user_b = _register(client, EMAIL_B)
    token_c, _ = _register(client, EMAIL_C)
    conversation_id = _friend_and_conversation(client, token_a, user_b["id"], token_b)
    message = _send_message(client, conversation_id, token_a)

    upload = client.post(
        f"/api/v1/attachments/upload/{message['id']}",
        headers=_auth(token_a),
        files={
            "file": (
                "note.txt.bin",
                b"hello" * 100,
                "application/octet-stream",
            )
        },
    )
    assert upload.status_code == 200, upload.text
    attachment_id = upload.json()["attachment"]["id"]

    # Outsider cannot download
    resp = client.get(
        f"/api/v1/attachments/{attachment_id}",
        headers=_auth(token_c),
    )
    assert resp.status_code == 403, resp.text

    # Outsider cannot delete
    resp = client.delete(
        f"/api/v1/attachments/{attachment_id}",
        headers=_auth(token_c),
    )
    assert resp.status_code == 403


def test_attachment_rejects_unsupported_extension(api_client):
    client = api_client
    token_a, _ = _register(client, EMAIL_A)
    token_b, user_b = _register(client, EMAIL_B)
    conversation_id = _friend_and_conversation(client, token_a, user_b["id"], token_b)
    message = _send_message(client, conversation_id, token_a)

    resp = client.post(
        f"/api/v1/attachments/upload/{message['id']}",
        headers=_auth(token_a),
        files={
            "file": (
                "evil.exe",
                b"MZ" * 512,
                "application/x-msdownload",
            )
        },
    )
    assert resp.status_code == 400, resp.text

    # Oversized `.bin` is rejected without reading it all into RAM
    huge = client.post(
        f"/api/v1/attachments/upload/{message['id']}",
        headers=_auth(token_a),
        files={
            "file": (
                "big.bin",
                b"\x00" * (500 * 1024 * 1024 + 1),
                "application/octet-stream",
            )
        },
    )
    assert huge.status_code == 400, huge.text