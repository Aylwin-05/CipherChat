"""User-scoped websocket (/ws/me) integration test for broadcast events."""

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
import app.websocket.ws as ws_module
from app.core.rate_limit import reset_limiter
from app.database.base import Base
from app.database.session import get_db
from app.main import app as app_instance

EMAIL_A = "alice@example.com"
EMAIL_B = "bob@example.com"
EMAIL_C = "carol@example.com"


class EmailRecorder:
    sent: list[dict] = []

    @classmethod
    async def send_otp_email(cls, recipient_email, otp, **kwargs):
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
        ws_module,
        "AsyncSessionLocal",
        TestingSessionLocal,
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
    data = resp.json()
    return data["access_token"], data["user"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _connect(client, token):
    """One user-scoped socket per client."""
    return client.websocket_connect(
        "/ws/me",
        subprotocols=["cipherchat." + token],
    )


def _drain(ws, target_event, limit=30):
    """Receive frames until an event matching target_event shows up."""
    for _ in range(limit):
        data = ws.receive_json()
        if data.get("event") == target_event:
            return data
    raise AssertionError(f"event '{target_event}' not received in {limit} frames")


def _drain_presence(ws, user_id, limit=30):
    """Receive frames until a presence event for a given user shows up."""
    for _ in range(limit):
        data = ws.receive_json()
        if (
            data.get("event") == "presence"
            and data.get("user_id") == user_id
        ):
            return data
    raise AssertionError(
        f"presence for '{user_id}' not received in {limit} frames"
    )


def _collect(ws, count):
    """DEBUG: receive exactly N frames and return them."""
    out = []
    for _ in range(count):
        out.append(ws.receive_json())
    return out


def _friend_and_conv(client, token_a, token_b, user_a_id, user_b_id):
    client.post(
        "/api/v1/friends/request",
        json={"receiver_id": str(user_b_id)},
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
    return client.post(
        "/api/v1/conversations/private",
        json={"user_id": str(user_b_id)},
        headers=_auth(token_a),
    ).json()


def _broadcast_message(ws, conversation_id, user_id, message_id, ciphertext, created_at, reply_to_id=None):
    ws.send_json({
        "event": "message",
        "id": message_id,
        "conversation_id": conversation_id,
        "sender_id": user_id,
        "ciphertext": ciphertext,
        "encrypted_key_sender": "ks1",
        "encrypted_key_receiver": "kr1",
        "nonce": "n1",
        "crypto_version": 1,
        "message_type": "text",
        "reply_to_id": reply_to_id,
        "is_forwarded": False,
        "edited": False,
        "deleted_for_everyone": False,
        "is_read": False,
        "created_at": created_at,
    })


def _save_message(client, token_a, conversation_id, ciphertext):
    resp = client.post(
        "/api/v1/messages/send",
        json={
            "conversation_id": conversation_id,
            "ciphertext": ciphertext,
            "encrypted_key_sender": "ks1",
            "encrypted_key_receiver": "kr1",
            "nonce": "n1",
            "reply_to_id": None,
        },
        headers=_auth(token_a),
    )
    return resp.json()


def test_ws_me_lifecycle(api_client):
    client = api_client
    token_a, user_a = _register(client, EMAIL_A)
    token_b, user_b = _register(client, EMAIL_B)

    conv = _friend_and_conv(
        client, token_a, token_b,
        user_a["id"], user_b["id"],
    )
    conversation_id = conv["id"]

    with _connect(client, token_a) as ws_a, _connect(client, token_b) as ws_b:

        ws_a.receive_json()  # connected (A)
        ws_b.receive_json()  # connected (B)
        _drain_presence(ws_a, str(user_b["id"]))  # B came online
        _drain_presence(ws_b, str(user_b["id"]))  # B's own echo
        _drain_presence(ws_b, str(user_a["id"]))  # snapshot: A already online

        # 0) Typing indicators reach the peer with conversation scope
        ws_a.send_json({"event": "typing", "conversation_id": conversation_id})
        ev = _drain(ws_b, "typing")
        assert ev["user_id"] == str(user_a["id"])
        assert ev["conversation_id"] == conversation_id
        ws_a.send_json({"event": "stop_typing", "conversation_id": conversation_id})
        ev = _drain(ws_b, "stop_typing")
        assert ev["user_id"] == str(user_a["id"])
        assert ev["conversation_id"] == conversation_id
        print("TYPING-BROADCAST: OK")

        # 1) Message: REST save + client WS broadcast (real client flow)
        saved = _save_message(client, token_a, conversation_id, "cipher-1")
        mid = saved["id"]
        _broadcast_message(
            ws_a, conversation_id, str(user_a["id"]),
            mid, "cipher-1", saved["created_at"],
        )
        ev_b = _drain(ws_b, "message")
        ev_a = _drain(ws_a, "message")
        print("MSG-BROADCAST:", ev_a.get("event"), ev_b.get("event"))
        assert ev_b["id"] == mid and ev_b["reply_to_id"] is None

        # 2) Reaction via REST (payload historically had raw UUIDs)
        r = client.put(
            f"/api/v1/messages/{mid}/reaction",
            json={"emoji": "1F60D"},
            headers=_auth(token_b),
        )
        print("REACT-REST:", r.json())
        ev_b = _drain(ws_b, "reaction")
        ev_a = _drain(ws_a, "reaction")
        print("REACT-BROADCAST:", ev_a, ev_b)
        assert ev_a["user_id"] == str(user_b["id"])
        assert ev_a["emoji"] == "1F60D"

        # 3) A follow-up message must STILL arrive (socket must not be dropped)
        saved2 = _save_message(client, token_a, conversation_id, "cipher-2")
        _broadcast_message(
            ws_a, conversation_id, str(user_a["id"]),
            saved2["id"], "cipher-2", saved2["created_at"],
        )
        ev_b = _drain(ws_b, "message")
        ev_a = _drain(ws_a, "message")
        print("AFTER-REACTION-MSG-BROADCAST: OK")
        assert ev_b["id"] == saved2["id"]

        # 4) Edit via REST. First B sends DELIVERED + READ receipts for
        #    the message (real client behaviour): the WS handler writes
        #    to the same row, so without the per-event commit this
        #    used to leave an open transaction holding the row lock,
        #    blocking the edit UPDATE until B's socket closed.
        ws_b.send_json({
            "event": "delivered",
            "conversation_id": conversation_id,
            "message_id": mid,
        })
        ev = _drain(ws_a, "delivered")
        assert ev["message_id"] == mid
        _drain(ws_b, "delivered")

        ws_b.send_json({
            "event": "read",
            "conversation_id": conversation_id,
            "message_id": mid,
        })
        ev = _drain(ws_a, "read")
        assert ev["message_id"] == mid
        _drain(ws_b, "read")

        client.put(
            f"/api/v1/messages/{mid}/edit",
            json={
                "ciphertext": "cipher-edited",
                "encrypted_key_sender": "ks2",
                "encrypted_key_receiver": "kr2",
                "nonce": "n2",
            },
            headers=_auth(token_a),
        )
        ev_b = _drain(ws_b, "edit")
        ev_a = _drain(ws_a, "edit")
        print("EDIT-BROADCAST:", ev_a.get("ciphertext"), ev_b.get("ciphertext"))
        assert ev_b["ciphertext"] == "cipher-edited"

        # 5) Delete for everyone: REST runs FIRST (soft-delete),
        #    then the sender's WS notify must STILL broadcast.
        client.delete(
            f"/api/v1/messages/{mid}",
            headers=_auth(token_a),
        )
        ws_a.send_json({
            "event": "delete",
            "conversation_id": conversation_id,
            "message_id": mid,
        })
        ev_b = _drain(ws_b, "delete")
        ev_a = _drain(ws_a, "delete")
        print("DELETE-BROADCAST:", ev_a, ev_b)
        assert ev_b["message_id"] == mid
        assert ev_b["deleted_for_everyone"] is True


def test_ws_call_signaling_relay(api_client):
    """WebRTC signaling (offer/answer/ice/end) is relayed between the
    members of a conversation; the server only stamps the sender id."""
    client = api_client
    token_a, user_a = _register(client, EMAIL_A)
    token_b, user_b = _register(client, EMAIL_B)

    conv = _friend_and_conv(
        client, token_a, token_b,
        user_a["id"], user_b["id"],
    )
    conversation_id = conv["id"]
    call_id = "call-1234"

    with _connect(client, token_a) as ws_a, _connect(client, token_b) as ws_b:

        ws_a.receive_json()  # connected (A)
        ws_b.receive_json()  # connected (B)
        _drain_presence(ws_a, str(user_b["id"]))
        _drain_presence(ws_b, str(user_b["id"]))
        _drain_presence(ws_b, str(user_a["id"]))

        # 1) A offers a video call -> B receives it with sender id
        ws_a.send_json({
            "event": "call_offer",
            "conversation_id": conversation_id,
            "call_id": call_id,
            "call_type": "video",
            "sdp": "fake-sdp-offer",
        })
        ev = _drain(ws_b, "call_offer")
        assert ev["call_id"] == call_id
        assert ev["call_type"] == "video"
        assert ev["from"] == str(user_a["id"])
        assert ev["sdp"] == "fake-sdp-offer"
        _drain(ws_a, "call_offer")  # sender's own echo (ignored client-side)

        # 2) B answers -> A receives it
        ws_b.send_json({
            "event": "call_answer",
            "conversation_id": conversation_id,
            "call_id": call_id,
            "to": str(user_a["id"]),
            "sdp": "fake-sdp-answer",
        })
        ev = _drain(ws_a, "call_answer")
        assert ev["call_id"] == call_id
        assert ev["from"] == str(user_b["id"])
        assert ev["sdp"] == "fake-sdp-answer"
        _drain(ws_b, "call_answer")

        # 3) ICE candidates flow both ways
        ws_a.send_json({
            "event": "call_ice",
            "conversation_id": conversation_id,
            "call_id": call_id,
            "to": str(user_b["id"]),
            "candidate": "candidate:1 1 udp 2130706431 192.168.1.5 54321 typ host",
        })
        ev = _drain(ws_b, "call_ice")
        assert ev["candidate"].startswith("candidate:")
        assert ev["from"] == str(user_a["id"])
        _drain(ws_a, "call_ice")

        # 4) A hangs up -> B receives call_end
        ws_a.send_json({
            "event": "call_end",
            "conversation_id": conversation_id,
            "call_id": call_id,
        })
        ev = _drain(ws_b, "call_end")
        assert ev["call_id"] == call_id
        assert ev["from"] == str(user_a["id"])
        _drain(ws_a, "call_end")

        # 5) Malformed signaling is rejected with a clear error
        ws_a.send_json({
            "event": "call_offer",
            "conversation_id": conversation_id,
        })
        ev = _drain(ws_a, "error")
        assert "call_id" in ev["message"]

        ws_a.send_json({
            "event": "call_offer",
            "conversation_id": conversation_id,
            "call_id": "call-2",
        })
        ev = _drain(ws_a, "error")
        assert "call_type" in ev["message"]

    print("CALL-RELAY: OK")


def test_ws_me_presence_three_users(api_client):
    """Presence is user-scoped: any member of a shared conversation
    sees online/offline, and non-members never do."""
    client = api_client
    token_a, user_a = _register(client, EMAIL_A)
    token_b, user_b = _register(client, EMAIL_B)
    token_c, user_c = _register(client, EMAIL_C)

    # A <-> B share one conversation; B <-> C share another
    _friend_and_conv(
        client, token_a, token_b,
        user_a["id"], user_b["id"],
    )
    _friend_and_conv(
        client, token_c, token_b,
        user_c["id"], user_b["id"],
    )

    with _connect(client, token_a) as ws_a:
        ws_a.receive_json()  # connected (A)
        with _connect(client, token_b) as ws_b:
            ws_b.receive_json()  # connected (B)
            # A must learn B is online (shared conversation)
            _drain_presence(ws_b, str(user_b["id"]))  # B's own echo
            ev = _drain_presence(ws_a, str(user_b["id"]))
            assert ev["online"] is True
            with _connect(client, token_c) as ws_c:
                ws_c.receive_json()  # connected (C)
                # B gets C's presence (shared conversation B<->C)...
                ev = _drain_presence(ws_b, str(user_c["id"]))
                assert ev["online"] is True
                # ...and C gets the snapshot: B already online.
                # (A is NOT a peer of C, so A never appears here.)
                _drain_presence(ws_c, str(user_c["id"]))  # C's own echo
                _drain_presence(ws_c, str(user_b["id"]))
            # C disconnected: B must receive the offline event
            ev = _drain_presence(ws_b, str(user_c["id"]))
            assert ev["online"] is False
        ev = _drain_presence(ws_a, str(user_b["id"]))
        assert ev["online"] is False
    print("PRESENCE-3-USER: OK")