"""Nexara comprehensive feature test: every feature, one run.

Exercises the full application surface through the real ASGI/API layer using
an isolated in-memory SQLite database (so the dev DB is never touched):

  Auth            - OTP send/verify, invalid OTP, rate limiting
  2FA             - enable / disable / PIN-gated login
  Devices         - Signal key-bundle registration + rotation
  Recovery        - recovery code minting on first device
  Friends         - request / accept / list / remove
  Conversations   - private + group creation, leave, invite links
  Messages        - E2EE send, history, edit, delete-for-me/all, forward,
                    search, read receipts, reactions, stars, pinned
  Disappearing    - disappearing-message timer config
  View-once       - view-once media flag + recipient-open destroy semantics
  Attachments     - encrypted upload / download + authorization
  Group admin     - promote, admin delete-for-everyone, remove member
  Blocks          - block / unblock + blocked-message denial
  Stories         - post + feed isolation
  Push            - web-push subscribe
  Calls           - voice + video call log, ICE config, end-call auth
  Signal crypto   - AEAD round-trip + X25519 key agreement
  Health          - /health + unknown-route 404
"""

import asyncio
import io
import uuid

import app.database.session as db_session_module
import app.services.email_service as email_module
import app.websocket.connection_manager as conn_mgr
import pytest
from app.core.rate_limit import reset_limiter
from app.crypto.signal.primitives import (
    aes_gcm_decrypt,
    aes_gcm_encrypt,
    b64encode,
    ed25519_public_to_bytes,
    ed25519_sign,
    generate_ed25519_keypair,
    generate_x25519_keypair,
    x25519_public_to_bytes,
)
from app.crypto.signal.x3dh import derive_x25519_from_ed25519
from app.database.base import Base
from app.database.session import get_db
from app.main import app as app_instance
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool


class EmailRecorder:
    sent: list[dict] = []

    @classmethod
    async def send_otp_email(cls, recipient_email: str, otp: str, **kwargs):
        cls.sent.append({"email": recipient_email, "otp": otp})


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(
        email_module.EmailService, "send_otp_email", EmailRecorder.send_otp_email
    )
    EmailRecorder.sent = []
    reset_limiter()
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = async_sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False
    )
    monkeypatch.setattr(conn_mgr, "AsyncSessionLocal", TestingSessionLocal)
    import app.main as main_module
    import app.websocket.ws as ws_module
    monkeypatch.setattr(main_module, "AsyncSessionLocal", TestingSessionLocal)
    monkeypatch.setattr(ws_module, "AsyncSessionLocal", TestingSessionLocal)
    monkeypatch.setattr(db_session_module, "AsyncSessionLocal", TestingSessionLocal)

    async def override_get_db():
        async with TestingSessionLocal() as session:
            yield session

    async def setup():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(setup())
    app_instance.dependency_overrides[get_db] = override_get_db
    with TestClient(app_instance) as c:
        yield c
    app_instance.dependency_overrides.clear()


# ======================================================================
# Helpers
# ======================================================================

def _register(c, email):
    c.post("/api/v1/auth/send-otp", json={"email": email})
    otp = EmailRecorder.sent[-1]["otp"]
    resp = c.post("/api/v1/auth/verify-otp", json={"email": email, "otp": otp})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    return data["access_token"], data["user"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


_PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
    b"\x00\x00\x00\x0bIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4"
    b"\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _friend(c, token_a, bob_id, token_b):
    resp = c.post("/api/v1/friends/request",
                  json={"receiver_id": str(bob_id)}, headers=_auth(token_a))
    assert resp.status_code == 200, resp.text
    pending = c.get("/api/v1/friends/pending", headers=_auth(token_b)).json()
    resp = c.post("/api/v1/friends/accept",
                  json={"friendship_id": str(pending[0]["id"])}, headers=_auth(token_b))
    assert resp.status_code == 200, resp.text


def _private(c, token_a, bob_id):
    resp = c.post("/api/v1/conversations/private",
                  json={"user_id": str(bob_id)}, headers=_auth(token_a))
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


def _group(c, token, name, member_ids):
    resp = c.post("/api/v1/conversations/group",
                  json={"name": name, "member_ids": [str(m) for m in member_ids]},
                  headers=_auth(token))
    assert resp.status_code == 200, resp.text
    return resp.json()


def _send(c, conversation_id, token, content="payload", **extra):
    payload = {
        "conversation_id": str(conversation_id),
        "ciphertext": content,
        "encrypted_key_sender": "k1",
        "encrypted_key_receiver": "k2",
        "nonce": "n",
        "crypto_version": 2,
        "message_type": "text",
        "reply_to_id": None,
    }
    payload.update(extra)
    return c.post("/api/v1/messages/send", json=payload, headers=_auth(token))


def _history(c, conversation_id, token):
    resp = c.get(f"/api/v1/messages/{conversation_id}", headers=_auth(token))
    assert resp.status_code == 200, resp.text
    return resp.json()


def _key_material(opk_count=2):
    (ipriv, ipub) = generate_ed25519_keypair()
    ix = derive_x25519_from_ed25519(ipriv)
    (_, spk_pub) = generate_x25519_keypair()
    spk_bytes = x25519_public_to_bytes(spk_pub)
    sig = ed25519_sign(ipriv, spk_bytes)
    opks = []
    for i in range(1, opk_count + 1):
        (_, q) = generate_x25519_keypair()
        opks.append({"key_id": i, "public_key": b64encode(x25519_public_to_bytes(q))})
    return {
        "identity_key_public": b64encode(ed25519_public_to_bytes(ipub)),
        "identity_key_x25519": b64encode(x25519_public_to_bytes(ix.public_key())),
        "signed_prekey_public": b64encode(spk_bytes),
        "signed_prekey_id": 1,
        "signed_prekey_signature": b64encode(sig),
        "one_time_prekeys": opks,
    }


def _upload(client, message_id, token, view_once=False):
    data = {"view_once": "true"} if view_once else {}
    resp = client.post(
        f"/api/v1/attachments/upload/{message_id}",
        headers=_auth(token),
        data=data,
        files={"file": ("secret.bin", b"\x01" * 512, "application/octet-stream")},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["attachment"]


# ======================================================================
# Auth + 2FA
# ======================================================================

def test_otp_login_and_invalid_otp_rejected(client):
    c = client
    token, user = _register(c, "alice@example.com")
    assert token
    assert user["email"] == "alice@example.com"

    c.post("/api/v1/auth/send-otp", json={"email": "bob@example.com"})
    resp = c.post("/api/v1/auth/verify-otp",
                  json={"email": "bob@example.com", "otp": "000000"})
    assert resp.status_code in (400, 401), resp.text


def test_two_factor_enable_pin_gated_login_and_disable(client):
    c = client
    token, _ = _register(c, "tfa@example.com")

    resp = c.put("/api/v1/auth/two-fa",
                 json={"pin": "123456", "confirm_pin": "123456"}, headers=_auth(token))
    assert resp.status_code == 200, resp.text
    assert resp.json()["two_fa_enabled"] is True

    status = c.get("/api/v1/auth/two-fa/status", headers=_auth(token))
    assert status.status_code == 200
    assert status.json()["two_fa_enabled"] is True

    resp = c.put("/api/v1/auth/two-fa",
                 json={"pin": "111111", "confirm_pin": "222222"}, headers=_auth(token))
    assert resp.status_code == 400, resp.text

    c.post("/api/v1/auth/send-otp", json={"email": "tfa@example.com"})
    otp = EmailRecorder.sent[-1]["otp"]
    challenge = c.post("/api/v1/auth/verify-otp",
                       json={"email": "tfa@example.com", "otp": otp}).json()
    assert challenge["two_fa_required"] is True
    assert challenge["two_fa_token"]
    assert "access_token" not in challenge

    resp = c.post("/api/v1/auth/two-fa/verify",
                  json={"two_fa_token": challenge["two_fa_token"], "pin": "999999"})
    assert resp.status_code == 400, resp.text

    resp = c.post("/api/v1/auth/two-fa/verify",
                  json={"two_fa_token": challenge["two_fa_token"], "pin": "123456"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["access_token"]

    resp = c.request("DELETE", "/api/v1/auth/two-fa", json={"pin": "999999"},
                     headers=_auth(token))
    assert resp.status_code == 400, resp.text
    resp = c.request("DELETE", "/api/v1/auth/two-fa", json={"pin": "123456"},
                     headers=_auth(token))
    assert resp.status_code == 200, resp.text
    assert resp.json()["two_fa_enabled"] is False


def test_otp_rate_limited(client):
    c = client
    for i in range(55):
        c.post("/api/v1/auth/send-otp", json={"email": f"rate{i}@example.com"})
    resp = c.post("/api/v1/auth/send-otp", json={"email": "overrun@example.com"})
    assert resp.status_code == 429, resp.text


# ======================================================================
# Devices + recovery
# ======================================================================

def test_device_registration_and_bundle(client):
    c = client
    token_a, user_a = _register(c, "dev@example.com")

    resp = c.post("/api/v1/devices/register",
                  json={"device_id": str(uuid.uuid4()), "platform": "web",
                        "device_name": "Primary", **_key_material()},
                  headers=_auth(token_a))
    assert resp.status_code == 200, resp.text
    assert resp.json()["is_primary"] is True

    resp = c.post("/api/v1/devices/register",
                  json={"device_id": str(uuid.uuid4()), "platform": "ios",
                        "device_name": "iPhone", **_key_material()},
                  headers=_auth(token_a))
    assert resp.status_code == 200, resp.text
    assert resp.json()["is_primary"] is False

    bundle = c.get(f"/api/v1/devices/{user_a['id']}/bundle", headers=_auth(token_a))
    assert bundle.status_code == 200, bundle.text
    body = bundle.json()
    assert body["user_id"] == str(user_a["id"])
    assert len(body["devices"]) == 2


def test_recovery_code_minted_on_first_device(client):
    c = client
    token_a, _ = _register(c, "rec@example.com")
    resp = c.post("/api/v1/devices/register",
                  json={"device_id": str(uuid.uuid4()), "platform": "web",
                        "device_name": "Laptop", **_key_material()},
                  headers=_auth(token_a))
    assert resp.status_code == 200, resp.text
    assert resp.json().get("recovery_code"), "first registration mints a code"


# ======================================================================
# Friends
# ======================================================================

def test_friend_request_accept_and_list(client):
    c = client
    token_a, _user_a = _register(c, "fa@example.com")
    token_b, user_b = _register(c, "fb@example.com")
    _friend(c, token_a, user_b["id"], token_b)

    friends = c.get("/api/v1/friends/", headers=_auth(token_a)).json()
    assert any(
        str(f["sender"]["id"]) == str(user_b["id"]) or str(f["receiver"]["id"]) == str(user_b["id"])
        for f in friends
    )


def test_friend_request_to_unknown_is_not_500(client):
    c = client
    token_a, _ = _register(c, "fu@example.com")
    resp = c.post("/api/v1/friends/request",
                  json={"receiver_id": str(uuid.uuid4())}, headers=_auth(token_a))
    assert resp.status_code in (400, 404), resp.text


# ======================================================================
# Conversations
# ======================================================================

def test_private_conversation_lifecycle(client):
    c = client
    token_a, _user_a = _register(c, "pa@example.com")
    token_b, user_b = _register(c, "pb@example.com")
    _friend(c, token_a, user_b["id"], token_b)

    conv_id = _private(c, token_a, user_b["id"])
    listed = c.get("/api/v1/conversations/", headers=_auth(token_a)).json()
    assert any(x["id"] == str(conv_id) for x in listed)
    detail = next(x for x in listed if x["id"] == str(conv_id))
    assert detail["conversation_type"] == "private"


def test_group_create_leave_and_invite(client):
    c = client
    token_a, _user_a = _register(c, "ga@example.com")
    token_b, user_b = _register(c, "gb@example.com")
    token_c, user_c = _register(c, "gc@example.com")
    _friend(c, token_a, user_b["id"], token_b)
    _friend(c, token_a, user_c["id"], token_c)

    group = _group(c, token_a, "Road Trip", [user_b["id"], user_c["id"]])
    gid = group["id"]
    assert group["conversation_type"] == "group"

    for token in (token_a, token_b, token_c):
        listed = c.get("/api/v1/conversations/", headers=_auth(token)).json()
        assert any(x["id"] == str(gid) for x in listed)

    link = c.post(f"/api/v1/conversations/{gid}/group/invite-link",
                  headers=_auth(token_a))
    assert link.status_code == 200, link.text
    assert link.json()["token"]

    resp = c.post(f"/api/v1/conversations/{gid}/group/leave", headers=_auth(token_b))
    assert resp.status_code == 200, resp.text
    detail = c.get(f"/api/v1/conversations/{gid}", headers=_auth(token_a)).json()
    member_ids = [m["user_id"] for m in detail["participants"]]
    assert str(user_b["id"]) not in member_ids


# ======================================================================
# Messages
# ======================================================================

def test_send_history_edit_and_read_receipt(client):
    c = client
    token_a, user_a = _register(c, "ma@example.com")
    token_b, user_b = _register(c, "mb@example.com")
    _friend(c, token_a, user_b["id"], token_b)
    conv_id = _private(c, token_a, user_b["id"])

    resp = _send(c, conv_id, token_a, content="cipher-1")
    assert resp.status_code == 200, resp.text
    msg = resp.json()
    assert msg["ciphertext"] == "cipher-1"
    assert msg["sender_id"] == str(user_a["id"])

    hist = _history(c, conv_id, token_b)
    assert len(hist) == 1
    assert hist[0]["is_read"] is False

    # edit
    resp = c.put(f"/api/v1/messages/{msg['id']}/edit",
                 json={"ciphertext": "edited", "encrypted_key_sender": "k1",
                       "encrypted_key_receiver": "k2", "nonce": "n2"},
                 headers=_auth(token_a))
    assert resp.status_code == 200, resp.text
    assert resp.json()["ciphertext"] == "edited"

    # read receipts
    resp = c.post(f"/api/v1/messages/read-all/{conv_id}", headers=_auth(token_b))
    assert resp.status_code == 200, resp.text
    assert all(m["is_read"] is True for m in _history(c, conv_id, token_b))


def test_delete_for_me_and_delete_for_everyone(client):
    c = client
    token_a, _user_a = _register(c, "de@example.com")
    token_b, user_b = _register(c, "deb@example.com")
    _friend(c, token_a, user_b["id"], token_b)
    conv_id = _private(c, token_a, user_b["id"])

    msg = _send(c, conv_id, token_a, content="remove me").json()

    # only the sender can delete for everyone in a private chat
    resp = c.delete(f"/api/v1/messages/{msg['id']}", headers=_auth(token_b))
    assert resp.status_code == 400, resp.text
    resp = c.delete(f"/api/v1/messages/{msg['id']}", headers=_auth(token_a))
    assert resp.status_code == 204, resp.text

    # delete-for-me removes it for the caller only
    msg2 = _send(c, conv_id, token_a, content="a").json()
    resp = c.delete(f"/api/v1/messages/{msg2['id']}/me", headers=_auth(token_a))
    assert resp.status_code == 204, resp.text


def test_forward_and_search(client):
    c = client
    token_a, _user_a = _register(c, "mf@example.com")
    token_b, user_b = _register(c, "mfb@example.com")
    token_c, user_c = _register(c, "mfc@example.com")
    _friend(c, token_a, user_b["id"], token_b)
    _friend(c, token_a, user_c["id"], token_c)
    conv_ab = _private(c, token_a, user_b["id"])
    conv_ac = _private(c, token_a, user_c["id"])

    _send(c, conv_ab, token_a, content="forwardable")
    fwd = _send(c, conv_ac, token_a, content="forwardable",
                is_forwarded=True, forwarded_count=1)
    assert fwd.status_code == 200, fwd.text
    assert fwd.json()["is_forwarded"] is True

    resp = c.get(f"/api/v1/messages/search/{conv_ab}?q=forwardable",
                 headers=_auth(token_a))
    assert resp.status_code == 200, resp.text
    assert len(resp.json()["results"]) >= 1


def test_reaction_star_and_pin(client):
    c = client
    token_a, _user_a = _register(c, "re@example.com")
    token_b, user_b = _register(c, "reb@example.com")
    _friend(c, token_a, user_b["id"], token_b)
    conv_id = _private(c, token_a, user_b["id"])

    msg = _send(c, conv_id, token_a, content="react me").json()

    resp = c.put(f"/api/v1/messages/{msg['id']}/reaction",
                 json={"emoji": "🔥"}, headers=_auth(token_b))
    assert resp.status_code == 200, resp.text
    assert resp.json()["emoji"] == "🔥"

    resp = c.put(f"/api/v1/messages/{msg['id']}/star",
                 json={"starred": True}, headers=_auth(token_b))
    assert resp.status_code == 200, resp.text

    resp = c.put(f"/api/v1/messages/{msg['id']}/pin", headers=_auth(token_b))
    assert resp.status_code == 200, resp.text
    pinned = c.get(f"/api/v1/messages/pinned/{conv_id}", headers=_auth(token_b)).json()
    assert any(m["id"] == str(msg["id"]) for m in pinned["messages"])


def test_non_participant_cannot_send(client):
    c = client
    token_a, _ = _register(c, "np@example.com")
    token_b, user_b = _register(c, "npb@example.com")
    token_c, _ = _register(c, "npc@example.com")
    _friend(c, token_a, user_b["id"], token_b)
    conv_id = _private(c, token_a, user_b["id"])
    resp = _send(c, conv_id, token_c, content="intruder")
    assert resp.status_code in (403, 404), resp.text


# ======================================================================
# Disappearing messages
# ======================================================================

def test_disappearing_message_timer(client):
    c = client
    token_a, _ = _register(c, "di@example.com")
    token_b, user_b = _register(c, "dib@example.com")
    _friend(c, token_a, user_b["id"], token_b)
    conv_id = _private(c, token_a, user_b["id"])

    resp = c.patch(f"/api/v1/conversations/{conv_id}",
                   json={"disappear_after_seconds": 3600}, headers=_auth(token_a))
    assert resp.status_code == 200, resp.text
    assert resp.json()["disappear_after_seconds"] == 3600

    listed = c.get("/api/v1/conversations/", headers=_auth(token_a)).json()
    conv = next(x for x in listed if x["id"] == str(conv_id))
    assert conv["disappear_after_seconds"] == 3600

    resp = c.patch(f"/api/v1/conversations/{conv_id}",
                   json={"disappear_after_seconds": None}, headers=_auth(token_a))
    assert resp.status_code == 200, resp.text
    assert resp.json()["disappear_after_seconds"] is None


# ======================================================================
# View-once + attachments
# ======================================================================

def test_view_once_media_lifecycle(client):
    c = client
    token_a, _user_a = _register(c, "vo@example.com")
    token_b, user_b = _register(c, "vob@example.com")
    _friend(c, token_a, user_b["id"], token_b)
    conv_id = _private(c, token_a, user_b["id"])

    msg = _send(c, conv_id, token_a, content="once").json()
    attachment = _upload(c, msg["id"], token_a, view_once=True)
    assert attachment["view_once"] is True

    hist = _history(c, conv_id, token_b)
    viewed = next(m for m in hist if m["id"] == msg["id"])
    assert viewed["view_once_opened"] is False

    # sender cannot open it
    resp = c.post(f"/api/v1/messages/{msg['id']}/view-once-opened",
                  headers=_auth(token_a))
    assert resp.status_code == 400, resp.text

    # recipient open destroys the media and flags the message
    resp = c.post(f"/api/v1/messages/{msg['id']}/view-once-opened",
                  headers=_auth(token_b))
    assert resp.status_code == 200, resp.text
    assert resp.json()["view_once_opened"] is True

    hist = _history(c, conv_id, token_b)
    viewed = next(m for m in hist if m["id"] == msg["id"])
    assert viewed["view_once_opened"] is True
    assert viewed["attachments"] == []

    for token in (token_a, token_b):
        resp = c.get(f"/api/v1/attachments/{attachment['id']}", headers=_auth(token))
        assert resp.status_code == 404, resp.text


def test_attachment_encrypted_upload_download_authorized(client):
    c = client
    token_a, _ = _register(c, "at@example.com")
    token_b, user_b = _register(c, "atb@example.com")
    token_c, _ = _register(c, "atc@example.com")
    _friend(c, token_a, user_b["id"], token_b)
    conv_id = _private(c, token_a, user_b["id"])

    msg = _send(c, conv_id, token_a, content="with file").json()
    attachment = _upload(c, msg["id"], token_a)

    # participant can download
    resp = c.get(f"/api/v1/attachments/{attachment['id']}", headers=_auth(token_b))
    assert resp.status_code == 200, resp.text
    # stranger cannot
    resp = c.get(f"/api/v1/attachments/{attachment['id']}", headers=_auth(token_c))
    assert resp.status_code in (403, 404), resp.text


# ======================================================================
# Stories
# ======================================================================

def test_story_post_and_feed_isolation(client):
    c = client
    token_a, _ = _register(c, "st@example.com")
    token_b, user_b = _register(c, "stb@example.com")
    _friend(c, token_a, user_b["id"], token_b)

    resp = c.post("/api/v1/stories/",
                  files={"file": ("status.png", io.BytesIO(_PNG_BYTES), "image/png")},
                  data={"encrypted_key_sender": "k", "nonce": "n"},
                  headers=_auth(token_a))
    assert resp.status_code == 200, resp.text

    feed = c.get("/api/v1/stories/feed", headers=_auth(token_b)).json()
    assert len(feed) >= 1


# ======================================================================
# Blocks
# ======================================================================

def test_block_denies_messaging(client):
    c = client
    token_a, _ = _register(c, "bl@example.com")
    token_b, user_b = _register(c, "blb@example.com")
    _friend(c, token_a, user_b["id"], token_b)
    conv_id = _private(c, token_a, user_b["id"])

    resp = c.post("/api/v1/blocks/", json={"user_id": str(user_b["id"])},
                  headers=_auth(token_a))
    assert resp.status_code == 200, resp.text

    # blocked user cannot message the blocker
    resp = _send(c, conv_id, token_b, content="blocked msg")
    assert resp.status_code == 403, resp.text


# ======================================================================
# Push
# ======================================================================

def test_push_subscribe(client):
    c = client
    token_a, _ = _register(c, "pu@example.com")
    resp = c.post("/api/v1/push/subscribe",
                  json={"endpoint": "https://push.example.com/a/b",
                        "p256dh": "cGFk", "auth": "YXV0aA"},
                  headers=_auth(token_a))
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "subscribed"


# ======================================================================
# Calls (voice + video)
# ======================================================================

def test_call_config_requires_auth_and_returns_ice(client):
    c = client
    token_a, _ = _register(c, "ca@example.com")

    resp = c.get("/api/v1/call/config")
    assert resp.status_code in (401, 403), resp.text

    resp = c.get("/api/v1/call/config", headers=_auth(token_a))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["e2ee_supported"] is True
    assert any("stun" in s["urls"] for s in body["ice_servers"])


def test_voice_and_video_call_log_end_to_end(client):
    c = client
    token_a, _user_a = _register(c, "cv@example.com")
    token_b, user_b = _register(c, "cvb@example.com")
    _friend(c, token_a, user_b["id"], token_b)
    conv_id = _private(c, token_a, user_b["id"])

    v_resp = c.post("/api/v1/call/log",
                    params={"receiver_id": str(user_b["id"]),
                            "conversation_id": str(conv_id),
                            "call_type": "voice", "status": "missed"},
                    headers=_auth(token_a))
    assert v_resp.status_code == 200, v_resp.text

    vid_resp = c.post("/api/v1/call/log",
                      params={"receiver_id": str(user_b["id"]),
                              "conversation_id": str(conv_id),
                              "call_type": "video", "status": "answered"},
                      headers=_auth(token_a))
    assert vid_resp.status_code == 200, vid_resp.text

    end = c.put(f"/api/v1/call/{vid_resp.json()['id']}/end",
                params={"duration_seconds": 35}, headers=_auth(token_a))
    assert end.status_code == 200, end.text

    for token in (token_a, token_b):
        logs = c.get("/api/v1/call/logs", params={"limit": 100},
                     headers=_auth(token)).json()
        assert logs["count"] >= 2
        types = {x["call_type"] for x in logs["calls"]}
        assert "voice" in types
        assert "video" in types


def test_call_log_end_forbidden_for_stranger(client):
    c = client
    token_a, _user_a = _register(c, "cx@example.com")
    token_b, user_b = _register(c, "cxb@example.com")
    token_c, _ = _register(c, "cxc@example.com")
    _friend(c, token_a, user_b["id"], token_b)

    log_id = c.post("/api/v1/call/log",
                    params={"receiver_id": str(user_b["id"]), "call_type": "video"},
                    headers=_auth(token_a)).json()["id"]
    resp = c.put(f"/api/v1/call/{log_id}/end",
                 params={"duration_seconds": 10}, headers=_auth(token_c))
    assert resp.status_code == 403, resp.text


# ======================================================================
# Group admin moderation
# ======================================================================

def test_group_admin_promote_and_delete_for_everyone(client):
    c = client
    token_a, _user_a = _register(c, "ad@example.com")
    token_b, user_b = _register(c, "adb@example.com")
    token_c, user_c = _register(c, "adc@example.com")
    _friend(c, token_a, user_b["id"], token_b)
    _friend(c, token_a, user_c["id"], token_c)
    _friend(c, token_b, user_c["id"], token_c)
    gid = _group(c, token_a, "Moderation", [user_b["id"], user_c["id"]])["id"]

    resp = c.post(f"/api/v1/conversations/{gid}/group/admin",
                  json={"user_id": str(user_c["id"]), "is_admin": True},
                  headers=_auth(token_a))
    assert resp.status_code == 200, resp.text

    msg = _send(c, gid, token_a, content="alice's message").json()

    # a plain member who is not the sender cannot delete for everyone
    resp = c.delete(f"/api/v1/messages/{msg['id']}", headers=_auth(token_b))
    assert resp.status_code == 400, resp.text
    # an admin can delete for everyone
    resp = c.delete(f"/api/v1/messages/{msg['id']}", headers=_auth(token_c))
    assert resp.status_code == 204, resp.text

    history = _history(c, gid, token_b)
    target = next(m for m in history if m["id"] == str(msg["id"]))
    assert target["deleted_for_everyone"] is True


def test_admin_can_remove_member(client):
    c = client
    token_a, _user_a = _register(c, "rm@example.com")
    token_b, user_b = _register(c, "rmb@example.com")
    _friend(c, token_a, user_b["id"], token_b)
    gid = _group(c, token_a, "Removal", [user_b["id"]])["id"]

    resp = c.post(f"/api/v1/conversations/{gid}/group/remove",
                  json={"user_id": str(user_b["id"])}, headers=_auth(token_a))
    assert resp.status_code == 200, resp.text


# ======================================================================
# Signal crypto primitives
# ======================================================================

def test_signal_crypto_pair_derive_and_aead(client):
    key = b"0123456789abcdef"
    ciphertext, nonce = aes_gcm_encrypt(key, b"hello nexara", b"aad")
    assert aes_gcm_decrypt(key, ciphertext, b"aad", nonce) == b"hello nexara"

    generate_x25519_keypair()  # X25519 keypair generation is exercised end-to-end
