"""API tests for group chats.

Group chat E2EE: every message is encrypted with a fresh
AES-256-GCM key wrapped per recipient (message_recipient_keys).
The backend only stores ciphertext + wrapped keys. The creator
is admin; admins add members; members can leave; a group whose
last member leaves ceases to exist.
"""

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
EMAIL_C = "carol@example.com"
EMAIL_D = "dave@example.com"


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


def _friend(client, token_a, bob_id, token_b):
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


def _friend_each_with(client, token_a, others):
    for token_b, other_id in others:
        _friend(client, token_a, other_id, token_b)


def _create_group(client, token, name, member_ids):
    resp = client.post(
        "/api/v1/conversations/group",
        json={"name": name, "member_ids": [str(m) for m in member_ids]},
        headers=_auth(token),
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _send_group(client, conversation_id, token, content="payload"):
    resp = client.post(
        "/api/v1/messages/send",
        json={
            "conversation_id": str(conversation_id),
            "ciphertext": content,
            "encrypted_key_sender": "k1",
            "encrypted_key_receiver": "k2",
            "nonce": "n",
            "recipient_keys": [
                {
                    "user_id": str(
                        _other_member_id(client, conversation_id, token)
                    ),
                    "encrypted_key": "wrapped",
                }
            ],
        },
        headers=_auth(token),
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _other_member_id(client, conversation_id, token):
    detail = client.get(
        f"/api/v1/conversations/{conversation_id}",
        headers=_auth(token),
    ).json()
    return detail["participants"][0]["user_id"]


def _group_detail(client, conversation_id, token):
    resp = client.get(
        f"/api/v1/conversations/{conversation_id}",
        headers=_auth(token),
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _conversations(client, token):
    resp = client.get(
        "/api/v1/conversations/",
        headers=_auth(token),
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


# ==========================================================
# Creation
# ==========================================================


def test_create_group_with_friends(api_client):
    client = api_client
    token_a, user_a = _register(client, EMAIL_A)
    token_b, user_b = _register(client, EMAIL_B)
    token_c, user_c = _register(client, EMAIL_C)

    _friend_each_with(
        client, token_a, [(token_b, user_b["id"]), (token_c, user_c["id"])]
    )

    group = _create_group(client, token_a, "Trip", [user_b["id"], user_c["id"]])

    assert group["conversation_type"] == "group"
    assert group["name"] == "Trip"
    assert group["participant_count"] == 3

    # Creator is admin, everyone else is a member
    detail = _group_detail(client, group["id"], token_a)
    assert detail["is_admin"] is True
    by_id = {p["user_id"]: p for p in detail["participants"]}
    assert by_id[str(user_a["id"])]["is_admin"] is True
    assert by_id[str(user_b["id"])]["is_admin"] is False
    assert by_id[str(user_c["id"])]["is_admin"] is False

    # Group appears in everyone's conversation list
    assert group["id"] in [c["id"] for c in _conversations(client, token_a)]
    assert group["id"] in [c["id"] for c in _conversations(client, token_b)]
    assert group["id"] in [c["id"] for c in _conversations(client, token_c)]

    listed = next(
        c for c in _conversations(client, token_a) if c["id"] == group["id"]
    )
    assert listed["conversation_type"] == "group"
    assert listed["name"] == "Trip"
    assert listed["participant_count"] == 3
    assert listed["other_user"] is None


def test_create_group_requires_friends(api_client):
    client = api_client
    token_a, user_a = _register(client, EMAIL_A)
    token_b, user_b = _register(client, EMAIL_B)

    # user_b is NOT a friend of user_a
    resp = client.post(
        "/api/v1/conversations/group",
        json={"name": "Sneaky", "member_ids": [str(user_b["id"])]},
        headers=_auth(token_a),
    )
    assert resp.status_code == 400
    assert "friends" in resp.json()["detail"]


def test_create_group_validation(api_client):
    client = api_client
    token_a, user_a = _register(client, EMAIL_A)
    token_b, user_b = _register(client, EMAIL_B)

    _friend(client, token_a, user_b["id"], token_b)

    # Empty name
    resp = client.post(
        "/api/v1/conversations/group",
        json={"name": "", "member_ids": [str(user_b["id"])]},
        headers=_auth(token_a),
    )
    assert resp.status_code in (400, 422)

    # No members
    resp = client.post(
        "/api/v1/conversations/group",
        json={"name": "Alone", "member_ids": []},
        headers=_auth(token_a),
    )
    assert resp.status_code in (400, 422)

    # Cannot add yourself
    resp = client.post(
        "/api/v1/conversations/group",
        json={"name": "Self", "member_ids": [str(user_a["id"])]},
        headers=_auth(token_a),
    )
    assert resp.status_code == 400

    # Duplicates collapse
    group = _create_group(
        client, token_a, "Dup", [user_b["id"], user_b["id"]]
    )
    assert group["participant_count"] == 2


# ==========================================================
# Group detail
# ==========================================================


def test_group_detail_exposes_public_keys(api_client):
    client = api_client
    token_a, user_a = _register(client, EMAIL_A)
    token_b, user_b = _register(client, EMAIL_B)

    _friend(client, token_a, user_b["id"], token_b)

    group = _create_group(client, token_a, "Keys", [user_b["id"]])

    detail = _group_detail(client, group["id"], token_a)
    assert len(detail["participants"]) == 2
    for p in detail["participants"]:
        assert "display_name" in p
        assert "username" in p
        assert "public_key" in p or p["public_key"] is None


def test_group_detail_rejects_non_participant(api_client):
    client = api_client
    token_a, user_a = _register(client, EMAIL_A)
    token_b, user_b = _register(client, EMAIL_B)
    token_c, user_c = _register(client, EMAIL_C)

    _friend_each_with(
        client, token_a, [(token_b, user_b["id"]), (token_c, user_c["id"])]
    )
    group = _create_group(client, token_a, "Closed", [user_b["id"]])

    resp = client.get(
        f"/api/v1/conversations/{group['id']}",
        headers=_auth(token_c),
    )
    assert resp.status_code == 403


def test_group_detail_rejects_private_conversation(api_client):
    client = api_client
    token_a, user_a = _register(client, EMAIL_A)
    token_b, user_b = _register(client, EMAIL_B)

    _friend(client, token_a, user_b["id"], token_b)

    resp = client.post(
        "/api/v1/conversations/private",
        json={"user_id": str(user_b["id"])},
        headers=_auth(token_a),
    )
    private_id = resp.json()["id"]

    resp = client.get(
        f"/api/v1/conversations/{private_id}",
        headers=_auth(token_a),
    )
    assert resp.status_code == 400


# ==========================================================
# Sending group messages with per-recipient keys
# ==========================================================


def test_group_message_stores_recipient_keys(api_client):
    client = api_client
    token_a, user_a = _register(client, EMAIL_A)
    token_b, user_b = _register(client, EMAIL_B)
    token_c, user_c = _register(client, EMAIL_C)

    _friend_each_with(
        client, token_a, [(token_b, user_b["id"]), (token_c, user_c["id"])]
    )
    group = _create_group(client, token_a, "Triple", [user_b["id"], user_c["id"]])

    message = _send_group(client, group["id"], token_a, "hello everyone")

    assert message["recipient_keys"]
    assert len(message["recipient_keys"]) >= 1

    # Every member can fetch history and receives the wrapped key
    for member_token in (token_b, token_c):
        history = client.get(
            f"/api/v1/messages/{group['id']}",
            headers=_auth(member_token),
        ).json()
        assert len(history) == 1
        assert history[0]["recipient_keys"]
        assert any(
            k["user_id"] == str(user_a["id"])
            for k in history[0]["recipient_keys"]
        )


def test_group_message_requires_membership(api_client):
    client = api_client
    token_a, user_a = _register(client, EMAIL_A)
    token_b, user_b = _register(client, EMAIL_B)
    token_c, user_c = _register(client, EMAIL_C)

    _friend_each_with(
        client, token_a, [(token_b, user_b["id"]), (token_c, user_c["id"])]
    )
    group = _create_group(client, token_a, "Exclusive", [user_b["id"]])

    # user_c is not in the group: cannot send
    resp = client.post(
        "/api/v1/messages/send",
        json={
            "conversation_id": str(group["id"]),
            "ciphertext": "intruder",
            "encrypted_key_sender": "k1",
            "encrypted_key_receiver": "k2",
            "nonce": "n",
        },
        headers=_auth(token_c),
    )
    assert resp.status_code == 400

    # ...and cannot read history
    resp = client.get(
        f"/api/v1/messages/{group['id']}",
        headers=_auth(token_c),
    )
    assert resp.status_code == 400


# ==========================================================
# Adding members (admin only)
# ==========================================================


def test_admin_adds_member(api_client):
    client = api_client
    token_a, user_a = _register(client, EMAIL_A)
    token_b, user_b = _register(client, EMAIL_B)
    token_c, user_c = _register(client, EMAIL_C)
    token_d, user_d = _register(client, EMAIL_D)

    _friend_each_with(
        client, token_a,
        [(token_b, user_b["id"]), (token_c, user_c["id"]), (token_d, user_d["id"])],
    )
    group = _create_group(client, token_a, "Growing", [user_b["id"]])

    resp = client.post(
        f"/api/v1/conversations/{group['id']}/group/add",
        json={"member_ids": [str(user_c["id"]), str(user_d["id"])]},
        headers=_auth(token_a),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["participant_count"] == 4

    detail = _group_detail(client, group["id"], token_c)
    assert detail["participant_count"] == 4


def test_non_admin_cannot_add_members(api_client):
    client = api_client
    token_a, user_a = _register(client, EMAIL_A)
    token_b, user_b = _register(client, EMAIL_B)
    token_c, user_c = _register(client, EMAIL_C)
    token_d, user_d = _register(client, EMAIL_D)

    _friend_each_with(
        client, token_a,
        [(token_b, user_b["id"]), (token_c, user_c["id"]), (token_d, user_d["id"])],
    )
    _friend(client, token_b, user_d["id"], token_d)
    group = _create_group(client, token_a, "Strict", [user_b["id"]])

    # user_b is a member but NOT an admin
    resp = client.post(
        f"/api/v1/conversations/{group['id']}/group/add",
        json={"member_ids": [str(user_d["id"])]},
        headers=_auth(token_b),
    )
    assert resp.status_code == 403


def test_add_member_requires_friendship(api_client):
    client = api_client
    token_a, user_a = _register(client, EMAIL_A)
    token_b, user_b = _register(client, EMAIL_B)
    token_c, user_c = _register(client, EMAIL_C)

    _friend_each_with(client, token_a, [(token_b, user_b["id"])])
    group = _create_group(client, token_a, "FriendsOnly", [user_b["id"]])

    # user_c is not a friend of the admin
    resp = client.post(
        f"/api/v1/conversations/{group['id']}/group/add",
        json={"member_ids": [str(user_c["id"])]},
        headers=_auth(token_a),
    )
    assert resp.status_code == 400


# ==========================================================
# Leaving
# ==========================================================


def test_member_leaves_group(api_client):
    client = api_client
    token_a, user_a = _register(client, EMAIL_A)
    token_b, user_b = _register(client, EMAIL_B)

    _friend(client, token_a, user_b["id"], token_b)
    group = _create_group(client, token_a, "Two", [user_b["id"]])

    resp = client.post(
        f"/api/v1/conversations/{group['id']}/group/leave",
        headers=_auth(token_b),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "left"

    detail = _group_detail(client, group["id"], token_a)
    assert detail["participant_count"] == 1
    assert str(user_b["id"]) not in [p["user_id"] for p in detail["participants"]]

    # Leaver lost access
    resp = client.get(
        f"/api/v1/conversations/{group['id']}",
        headers=_auth(token_b),
    )
    assert resp.status_code == 403


def test_last_member_leaving_deletes_group(api_client):
    client = api_client
    token_a, user_a = _register(client, EMAIL_A)
    token_b, user_b = _register(client, EMAIL_B)

    _friend(client, token_a, user_b["id"], token_b)
    group = _create_group(client, token_a, "Doomed", [user_b["id"]])

    # Creator leaves first: the group survives with user_b
    resp = client.post(
        f"/api/v1/conversations/{group['id']}/group/leave",
        headers=_auth(token_a),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "left"
    assert group["id"] in [c["id"] for c in _conversations(client, token_b)]

    # The last remaining member leaves: the group ceases to exist
    resp = client.post(
        f"/api/v1/conversations/{group['id']}/group/leave",
        headers=_auth(token_b),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "deleted"

    assert group["id"] not in [c["id"] for c in _conversations(client, token_b)]


def test_leave_reassigns_admin_to_remaining_member(api_client):
    client = api_client
    token_a, user_a = _register(client, EMAIL_A)
    token_b, user_b = _register(client, EMAIL_B)
    token_c, user_c = _register(client, EMAIL_C)

    _friend_each_with(
        client, token_a, [(token_b, user_b["id"]), (token_c, user_c["id"])]
    )
    group = _create_group(client, token_a, "Legacy", [user_b["id"], user_c["id"]])

    # Creator leaves: the earliest-joined remaining member (b) becomes admin
    resp = client.post(
        f"/api/v1/conversations/{group['id']}/group/leave",
        headers=_auth(token_a),
    )
    assert resp.status_code == 200, resp.text

    detail = _group_detail(client, group["id"], token_b)
    by_id = {p["user_id"]: p for p in detail["participants"]}
    assert by_id[str(user_b["id"])]["is_admin"] is True
    assert detail["is_admin"] is True


def test_cannot_leave_private_conversation(api_client):
    client = api_client
    token_a, user_a = _register(client, EMAIL_A)
    token_b, user_b = _register(client, EMAIL_B)

    _friend(client, token_a, user_b["id"], token_b)
    resp = client.post(
        "/api/v1/conversations/private",
        json={"user_id": str(user_b["id"])},
        headers=_auth(token_a),
    )
    private_id = resp.json()["id"]

    resp = client.post(
        f"/api/v1/conversations/{private_id}/group/leave",
        headers=_auth(token_a),
    )
    assert resp.status_code == 400


# ==========================================================
# Guards
# ==========================================================


def test_two_party_delete_rejected_for_groups(api_client):
    client = api_client
    token_a, user_a = _register(client, EMAIL_A)
    token_b, user_b = _register(client, EMAIL_B)

    _friend(client, token_a, user_b["id"], token_b)
    group = _create_group(client, token_a, "KeepMe", [user_b["id"]])

    resp = client.post(
        f"/api/v1/conversations/{group['id']}/delete-request",
        headers=_auth(token_a),
    )
    assert resp.status_code == 400

    # Group still exists for both
    assert group["id"] in [c["id"] for c in _conversations(client, token_a)]
    assert group["id"] in [c["id"] for c in _conversations(client, token_b)]
