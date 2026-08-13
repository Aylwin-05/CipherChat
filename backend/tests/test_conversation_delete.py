"""API tests for two-party conversation deletion.

User 1 requests the wipe -> the OTHER participant must confirm
before anything is erased. On mutual consent the server purges
every message, attachment (rows and physical files) and the
conversation itself. Friendships survive.
"""

import asyncio
import os
from pathlib import Path

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


def _request_delete(client, conversation_id, token):
    return client.post(
        f"/api/v1/conversations/{conversation_id}/delete-request",
        headers=_auth(token),
    )


def _confirm_delete(client, conversation_id, token):
    return client.post(
        f"/api/v1/conversations/{conversation_id}/delete-confirm",
        headers=_auth(token),
    )


def _cancel_delete(client, conversation_id, token):
    return client.post(
        f"/api/v1/conversations/{conversation_id}/delete-cancel",
        headers=_auth(token),
    )


def _conversation_ids(client, token):
    data = client.get(
        "/api/v1/conversations/",
        headers=_auth(token),
    ).json()
    return [item["id"] for item in data]


def _friend_ids(client, token):
    data = client.get(
        "/api/v1/friends/",
        headers=_auth(token),
    ).json()
    return [item.get("id") or item.get("friendship_id") for item in data]


# ==========================================================
# Basic flow
# ==========================================================


def test_request_then_confirm_wipes_everything(api_client):
    client = api_client
    token_a, user_a = _register(client, EMAIL_A)
    token_b, user_b = _register(client, EMAIL_B)

    conv = _friend_and_conversation(client, token_a, user_b["id"], token_b)
    _send(client, conv, token_a, "hello bob")
    _send(client, conv, token_b, "hello alice")

    # User A requests deletion; nothing is erased yet
    resp = _request_delete(client, conv, token_a)
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "requested"
    assert resp.json()["delete_requested_by"] == user_a["id"]

    # Both still see the conversation and its messages
    assert conv in _conversation_ids(client, token_a)
    assert conv in _conversation_ids(client, token_b)
    hist = client.get(
        f"/api/v1/messages/{conv}",
        headers=_auth(token_a),
    ).json()
    assert len(hist) == 2

    # User B confirms -> full wipe
    resp = _confirm_delete(client, conv, token_b)
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "deleted"

    # Conversation + messages gone for BOTH users. Fetching
    # history of a purged conversation now errors: no rows remain.
    assert conv not in _conversation_ids(client, token_a)
    assert conv not in _conversation_ids(client, token_b)
    hist = client.get(
        f"/api/v1/messages/{conv}",
        headers=_auth(token_a),
    )
    assert hist.status_code in (400, 404)


def test_friendship_survives_conversation_delete(api_client):
    client = api_client
    token_a, user_a = _register(client, EMAIL_A)
    token_b, user_b = _register(client, EMAIL_B)

    conv = _friend_and_conversation(client, token_a, user_b["id"], token_b)
    _send(client, conv, token_a, "hi")

    _request_delete(client, conv, token_a)
    _confirm_delete(client, conv, token_b)

    assert len(_friend_ids(client, token_a)) == 1
    assert len(_friend_ids(client, token_b)) == 1


def test_mutual_simultaneous_requests_delete_immediately(api_client):
    client = api_client
    token_a, user_a = _register(client, EMAIL_A)
    token_b, user_b = _register(client, EMAIL_B)

    conv = _friend_and_conversation(client, token_a, user_b["id"], token_b)
    _send(client, conv, token_a, "hi")

    # A requests...
    resp = _request_delete(client, conv, token_a)
    assert resp.json()["status"] == "requested"

    # ...then B's own request completes the mutual consent
    resp = _request_delete(client, conv, token_b)
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "deleted"

    assert conv not in _conversation_ids(client, token_a)
    assert conv not in _conversation_ids(client, token_b)


def test_duplicate_request_is_idempotent(api_client):
    client = api_client
    token_a, user_a = _register(client, EMAIL_A)
    token_b, user_b = _register(client, EMAIL_B)

    conv = _friend_and_conversation(client, token_a, user_b["id"], token_b)

    resp = _request_delete(client, conv, token_a)
    assert resp.json()["status"] == "requested"

    resp = _request_delete(client, conv, token_a)
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "requested"
    assert resp.json()["delete_requested_by"] == user_a["id"]


# ==========================================================
# Guards
# ==========================================================


def test_confirm_without_pending_request_is_rejected(api_client):
    client = api_client
    token_a, user_a = _register(client, EMAIL_A)
    token_b, user_b = _register(client, EMAIL_B)

    conv = _friend_and_conversation(client, token_a, user_b["id"], token_b)

    resp = _confirm_delete(client, conv, token_b)
    assert resp.status_code == 400

    # Nothing was deleted
    assert conv in _conversation_ids(client, token_a)


def test_requester_cannot_self_confirm(api_client):
    client = api_client
    token_a, user_a = _register(client, EMAIL_A)
    token_b, user_b = _register(client, EMAIL_B)

    conv = _friend_and_conversation(client, token_a, user_b["id"], token_b)

    _request_delete(client, conv, token_a)

    resp = _confirm_delete(client, conv, token_a)
    assert resp.status_code == 400

    resp = _cancel_delete(client, conv, token_a)
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"

    # Cancelled request cannot be confirmed anymore
    resp = _confirm_delete(client, conv, token_b)
    assert resp.status_code == 400


def test_other_user_can_cancel_pending_request(api_client):
    client = api_client
    token_a, user_a = _register(client, EMAIL_A)
    token_b, user_b = _register(client, EMAIL_B)

    conv = _friend_and_conversation(client, token_a, user_b["id"], token_b)

    _request_delete(client, conv, token_a)

    # User B presses "Not now"
    resp = _cancel_delete(client, conv, token_b)
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"

    # The pending state is cleared for A as well
    listed = client.get(
        "/api/v1/conversations/",
        headers=_auth(token_a),
    ).json()
    item = next(item for item in listed if item["id"] == conv)
    assert item["delete_requested_by"] is None


def test_non_participant_cannot_request(api_client):
    client = api_client
    token_a, user_a = _register(client, EMAIL_A)
    token_b, user_b = _register(client, EMAIL_B)
    token_c, user_c = _register(client, EMAIL_C)

    conv = _friend_and_conversation(client, token_a, user_b["id"], token_b)

    resp = _request_delete(client, conv, token_c)
    assert resp.status_code == 403

    resp = _confirm_delete(client, conv, token_c)
    assert resp.status_code == 403

    conv_c = client.post(
        "/api/v1/conversations/private",
        json={"user_id": str(user_c["id"])},
        headers=_auth(token_a),
    )
    assert conv_c.status_code == 200
    conv_c_id = conv_c.json()["id"]
    _send(client, conv_c_id, token_a, "c only")
    _request_delete(client, conv_c_id, token_a)
    _confirm_delete(client, conv_c_id, token_c)
    assert conv_c_id not in _conversation_ids(client, token_a)


# ==========================================================
# Attachments
# ==========================================================


def test_delete_purges_attachment_rows_and_files(api_client):
    client = api_client
    token_a, user_a = _register(client, EMAIL_A)
    token_b, user_b = _register(client, EMAIL_B)

    conv = _friend_and_conversation(client, token_a, user_b["id"], token_b)
    message = _send(client, conv, token_a, "with a file")

    resp = client.post(
        f"/api/v1/attachments/upload/{message['id']}",
        files={
            "file": (
                "pic.jpg",
                b"\xff\xd8\xff\xe0fake-jpeg-data",
                "image/jpeg",
            )
        },
        headers=_auth(token_a),
    )
    assert resp.status_code == 200, resp.text
    storage_path = resp.json()["attachment"]["storage_path"]
    attachment_id = str(resp.json()["attachment"]["id"])

    file_path = Path(storage_path)
    assert file_path.exists()

    _request_delete(client, conv, token_a)
    _confirm_delete(client, conv, token_b)

    assert not file_path.exists()

    # Attachment row is gone: downloading must 404
    resp = client.get(
        f"/api/v1/attachments/{attachment_id}",
        headers=_auth(token_b),
    )
    assert resp.status_code == 404