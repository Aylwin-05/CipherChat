"""Tests for the account recovery code + sync copies feature."""

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
from app.services.recovery_service import unlock_sync_secret

EMAIL_A = "alice@example.com"
EMAIL_B = "bob@example.com"


class EmailRecorder:
    sent: list[dict] = []

    @classmethod
    async def send_otp_email(cls, recipient_email: str, otp: str, **kwargs):
        cls.sent.append({"email": recipient_email, "otp": otp})

    @classmethod
    async def send_recovery_code_email(cls, recipient_email: str, code: str, **kwargs):
        cls.sent.append({"email": recipient_email, "code": code})


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


def _friend_and_conversation(client, token_a, bob_id, token_b):
    client.post(
        "/api/v1/friends/request",
        json={"receiver_id": str(bob_id)},
        headers=_auth(token_a),
    )
    pending = client.get(
        "/api/v1/friends/pending",
        headers=_auth(token_b),
    ).json()
    client.post(
        "/api/v1/friends/accept",
        json={"friendship_id": str(pending[0]["id"])},
        headers=_auth(token_b),
    )
    resp = client.post(
        "/api/v1/conversations/private",
        json={"user_id": str(bob_id)},
        headers=_auth(token_a),
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _send(client, token, conversation_id, ciphertext="encrypted-payload"):
    resp = client.post(
        "/api/v1/messages/send",
        json={
            "conversation_id": str(conversation_id),
            "ciphertext": ciphertext,
            "encrypted_key_sender": "signal",
            "encrypted_key_receiver": "signal",
            "nonce": "signal",
            "message_type": "text",
        },
        headers=_auth(token),
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


# ==========================================================
# Recovery code lifecycle
# ==========================================================

def test_recovery_code_created_once_and_emailed(api_client):
    token_a, _ = _register(api_client, EMAIL_A)

    first = _register_device(api_client, token_a, str(uuid.uuid4()))
    assert first["recovery_code"] is not None
    assert first["recovery_salt"] is not None
    assert first["recovery_wrapped_key"] is not None

    recovery_emails = [
        item for item in EmailRecorder.sent
        if "code" in item
    ]
    assert any(
        item["email"] == EMAIL_A and item["code"] == first["recovery_code"].replace("-", "")
        for item in recovery_emails
    )

    second = _register_device(api_client, token_a, str(uuid.uuid4()))
    assert second["recovery_code"] is None

    unlock = api_client.get(
        "/api/v1/recovery/unlock",
        headers=_auth(token_a),
    )
    assert unlock.status_code == 200
    assert unlock.json()["salt"] == first["recovery_salt"]
    assert unlock.json()["wrapped_key"] == first["recovery_wrapped_key"]


def test_recovery_code_unlocks_sync_secret(api_client):
    token_a, _ = _register(api_client, EMAIL_A)
    first = _register_device(api_client, token_a, str(uuid.uuid4()))

    code = first["recovery_code"].replace("-", "")
    secret = unlock_sync_secret(
        code,
        first["recovery_salt"],
        first["recovery_wrapped_key"],
    )
    assert secret is not None
    assert len(secret) > 0

    assert unlock_sync_secret(
        "WRONGCODEWRONGCODEWRONG",
        first["recovery_salt"],
        first["recovery_wrapped_key"],
    ) is None


def test_profile_exposes_has_recovery_key(api_client):
    token_a, user_a = _register(api_client, EMAIL_A)

    me = api_client.get(
        "/api/v1/users/me",
        headers=_auth(token_a),
    ).json()
    assert me["has_recovery_key"] is False

    _register_device(api_client, token_a, str(uuid.uuid4()))

    me = api_client.get(
        "/api/v1/users/me",
        headers=_auth(token_a),
    ).json()
    assert me["has_recovery_key"] is True


# ==========================================================
# Sync envelope (messages)
# ==========================================================

def test_sync_envelope_upsert_and_fetch(api_client):
    token_a, user_a = _register(api_client, EMAIL_A)
    token_b, user_b = _register(api_client, EMAIL_B)
    conversation = _friend_and_conversation(
        api_client, token_a, user_b["id"], token_b
    )

    message = _send(api_client, token_a, conversation["id"])
    assert message["sync_envelope"] is None

    envelope = {"nonce": "abc", "data": "def", "ciphertext": "encrypted-payload"}

    resp = api_client.put(
        f"/api/v1/messages/{message['id']}/sync-envelope",
        json={"sync_copy": envelope},
        headers=_auth(token_a),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["sync_envelope"] == envelope

    history = api_client.get(
        f"/api/v1/messages/{conversation['id']}",
        headers=_auth(token_a),
    ).json()
    assert history[0]["sync_envelope"] == envelope

    # A non-participant cannot write sync copies.
    token_c, user_c = _register(api_client, "mallory@example.com")
    resp = api_client.put(
        f"/api/v1/messages/{message['id']}/sync-envelope",
        json={"sync_copy": {"nonce": "x", "data": "y"}},
        headers=_auth(token_c),
    )
    assert resp.status_code == 400


def test_sync_envelope_cleared_on_delete_for_everyone(api_client):
    token_a, user_a = _register(api_client, EMAIL_A)
    token_b, user_b = _register(api_client, EMAIL_B)
    conversation = _friend_and_conversation(
        api_client, token_a, user_b["id"], token_b
    )

    message = _send(api_client, token_a, conversation["id"])

    api_client.put(
        f"/api/v1/messages/{message['id']}/sync-envelope",
        json={"sync_copy": {"nonce": "abc", "data": "def"}},
        headers=_auth(token_a),
    )

    api_client.delete(
        f"/api/v1/messages/{message['id']}",
        headers=_auth(token_a),
    )

    history = api_client.get(
        f"/api/v1/messages/{conversation['id']}",
        headers=_auth(token_a),
    ).json()
    assert history[0]["sync_envelope"] is None


def test_sync_envelope_replaced_on_edit(api_client):
    token_a, user_a = _register(api_client, EMAIL_A)
    token_b, user_b = _register(api_client, EMAIL_B)
    conversation = _friend_and_conversation(
        api_client, token_a, user_b["id"], token_b
    )

    message = _send(api_client, token_a, conversation["id"])

    api_client.put(
        f"/api/v1/messages/{message['id']}/sync-envelope",
        json={"sync_copy": {"nonce": "old", "data": "old-data"}},
        headers=_auth(token_a),
    )

    resp = api_client.put(
        f"/api/v1/messages/{message['id']}/edit",
        json={
            "ciphertext": "new-ciphertext",
            "encrypted_key_sender": "signal",
            "encrypted_key_receiver": "signal",
            "nonce": "signal",
            "sync_envelope": {
                "nonce": "new",
                "data": "new-data",
                "ciphertext": "new-ciphertext",
            },
        },
        headers=_auth(token_a),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["sync_envelope"] == {
        "nonce": "new",
        "data": "new-data",
        "ciphertext": "new-ciphertext",
    }


# ==========================================================
# Sync blob (attachments)
# ==========================================================

def test_sync_blob_upsert_and_fetch(api_client):
    token_a, user_a = _register(api_client, EMAIL_A)
    token_b, user_b = _register(api_client, EMAIL_B)
    conversation = _friend_and_conversation(
        api_client, token_a, user_b["id"], token_b
    )

    message = _send(api_client, token_a, conversation["id"])

    upload = api_client.post(
        f"/api/v1/attachments/upload/{message['id']}",
        files={"file": ("photo.png", b"\x89PNG\r\n", "image/png")},
        data={
            "encrypted": "true",
            "encrypted_key_sender": "signal",
            "encrypted_key_receiver": "signal",
            "nonce": "signal",
        },
        headers=_auth(token_a),
    )
    assert upload.status_code == 200, upload.text
    attachment_id = upload.json()["attachment"]["id"]

    resp = api_client.put(
        f"/api/v1/attachments/{attachment_id}/sync-blob",
        json={"sync_copy": {"nonce": "abc", "data": "def"}},
        headers=_auth(token_a),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["sync_blob"] == {"nonce": "abc", "data": "def"}

    history = api_client.get(
        f"/api/v1/messages/{conversation['id']}",
        headers=_auth(token_a),
    ).json()
    assert history[0]["attachments"][0]["sync_blob"] == {
        "nonce": "abc",
        "data": "def",
    }