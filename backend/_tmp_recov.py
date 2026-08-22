

import asyncio
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool
import app.services.email_service as email_module
import app.websocket.connection_manager as conn_mgr
from app.core.rate_limit import reset_limiter
from app.database.base import Base
from app.database.session import get_db
from app.main import app as app_instance
import io
import os
from pathlib import Path
import time
from datetime import datetime, timedelta, timezone
import uuid
from cryptography.fernet import Fernet
from app.api.v1.api import api_router
from app.crypto.signal.primitives import b64encode, ed25519_public_to_bytes, ed25519_sign, generate_ed25519_keypair, generate_x25519_keypair, x25519_public_to_bytes
from app.crypto.signal.x3dh import derive_x25519_from_ed25519
from app.dependencies.auth import get_current_user
from app.models.user import User
import app.services.encryption_service as encryption_service_module
from sqlalchemy import delete
from app.dependencies.rate_limit import _client_ip as limiter_client_ip
from app.models.refresh_token import RefreshToken
from app.repositories.refresh_token_repository import RefreshTokenRepository
import base64
import json
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from http_ece import decrypt as ece_decrypt
import app.database.session as db_session_module
from app.services.recovery_service import unlock_sync_secret, recovery_token_store
from app.services.recovery_service import unlock_sync_secret
from app.crypto.signal.primitives import generate_x25519_keypair, generate_ed25519_keypair, x25519_dh, x25519_public_to_bytes, ed25519_public_to_bytes, ed25519_sign, ed25519_verify, kdf_root_chain, kdf_chain_key, aes_gcm_encrypt, aes_gcm_decrypt, generate_symmetric_key, generate_nonce
from app.crypto.signal.double_ratchet import kdf_root_chain_step, kdf_chain_key_step, derive_message_keys, DoubleRatchetCore, RatchetState, DHKeyPair, Chain
from app.crypto.signal.message import SignalEnvelope, EnvelopeError, build_prekey_message, parse_prekey_message
from app.crypto.signal.session import SignalSessionManager, InMemorySessionStore
from app.crypto.signal.primitives import generate_ed25519_keypair, generate_x25519_keypair, ed25519_private_to_bytes, x25519_private_to_bytes, b64encode
from app.crypto.signal.x3dh import create_key_bundle
from app.crypto.signal.double_ratchet import RatchetState
import app.websocket.ws as ws_module

# ======================================================================
# source: tests/test_admin_moderation.py
# ======================================================================
"API tests for WhatsApp-style group admin moderation.\n\nA group admin can delete any member's message for everyone;\nnon-admins (and non-senders) cannot.\n"
EMAIL_A = 'alice@example.com'
EMAIL_B = 'bob@example.com'
EMAIL_C = 'carol@example.com'
class EmailRecorder:
    sent: list[dict] = []

    @classmethod
    async def send_otp_email(cls, recipient_email: str, otp: str, **kwargs):
        cls.sent.append({'email': recipient_email, 'otp': otp})
@pytest.fixture
def api_client(monkeypatch):
    monkeypatch.setattr(email_module.EmailService, 'send_otp_email', EmailRecorder.send_otp_email)
    EmailRecorder.sent = []
    reset_limiter()
    engine = create_async_engine('sqlite+aiosqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    TestingSessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr(conn_mgr, 'AsyncSessionLocal', TestingSessionLocal)

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
    client.post('/api/v1/auth/send-otp', json={'email': email})
    otp = EmailRecorder.sent[-1]['otp']
    resp = client.post('/api/v1/auth/verify-otp', json={'email': email, 'otp': otp})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    return (data['access_token'], data['user'])
def _auth(token):
    return {'Authorization': f'Bearer {token}'}
def _friend(client, token_a, bob_id, token_b):
    resp = client.post('/api/v1/friends/request', json={'receiver_id': str(bob_id)}, headers=_auth(token_a))
    assert resp.status_code == 200, resp.text
    pending = client.get('/api/v1/friends/pending', headers=_auth(token_b)).json()
    friendship_id = pending[0]['id']
    resp = client.post('/api/v1/friends/accept', json={'friendship_id': str(friendship_id)}, headers=_auth(token_b))
    assert resp.status_code == 200, resp.text
def _create_group(client, token, name, member_ids):
    resp = client.post('/api/v1/conversations/group', json={'name': name, 'member_ids': [str(m) for m in member_ids]}, headers=_auth(token))
    assert resp.status_code == 200, resp.text
    return resp.json()
def _send(client, conversation_id, token, content='payload'):
    return client.post('/api/v1/messages/send', json={'conversation_id': str(conversation_id), 'ciphertext': content, 'encrypted_key_sender': 'k1', 'encrypted_key_receiver': 'k2', 'nonce': 'n'}, headers=_auth(token))
def _delete_everyone(client, token, message_id):
    return client.delete(f'/api/v1/messages/{message_id}', headers=_auth(token))
def test_group_admin_can_delete_any_members_message(api_client):
    client = api_client
    (token_a, user_a) = _register(client, EMAIL_A)
    (token_b, user_b) = _register(client, EMAIL_B)
    (token_c, user_c) = _register(client, EMAIL_C)
    _friend(client, token_a, user_b['id'], token_b)
    _friend(client, token_a, user_c['id'], token_c)
    _friend(client, token_b, user_c['id'], token_c)
    group = _create_group(client, token_a, 'Moderation', [user_b['id'], user_c['id']])
    conversation_id = group['id']
    sent = _send(client, conversation_id, token_b, content='bob says hi')
    assert sent.status_code == 200, sent.text
    message_id = sent.json()['id']
    resp = _delete_everyone(client, token_c, message_id)
    assert resp.status_code == 400
    resp = _delete_everyone(client, token_a, message_id)
    assert resp.status_code == 204, resp.text
    history = client.get(f'/api/v1/messages/{conversation_id}', headers=_auth(token_b)).json()
    target = next((message for message in history if message['id'] == str(message_id)))
    assert target['deleted_for_everyone'] is True
def test_promoted_admin_can_delete(api_client):
    client = api_client
    (token_a, user_a) = _register(client, EMAIL_A)
    (token_b, user_b) = _register(client, EMAIL_B)
    (token_c, user_c) = _register(client, EMAIL_C)
    _friend(client, token_a, user_b['id'], token_b)
    _friend(client, token_a, user_c['id'], token_c)
    _friend(client, token_b, user_c['id'], token_c)
    group = _create_group(client, token_a, 'Promoted', [user_b['id'], user_c['id']])
    conversation_id = group['id']
    resp = client.post(f'/api/v1/conversations/{conversation_id}/group/admin', json={'user_id': str(user_c['id']), 'is_admin': True}, headers=_auth(token_a))
    assert resp.status_code == 200, resp.text
    sent = _send(client, conversation_id, token_b, content='bob again')
    message_id = sent.json()['id']
    resp = _delete_everyone(client, token_c, message_id)
    assert resp.status_code == 204, resp.text
def test_non_sender_cannot_delete_in_private_chat(api_client):
    client = api_client
    (token_a, user_a) = _register(client, EMAIL_A)
    (token_b, user_b) = _register(client, EMAIL_B)
    _friend(client, token_a, user_b['id'], token_b)
    resp = client.post('/api/v1/conversations/private', json={'user_id': str(user_b['id'])}, headers=_auth(token_a))
    assert resp.status_code == 200, resp.text
    conversation_id = resp.json()['id']
    sent = _send(client, conversation_id, token_a, content='private note')
    message_id = sent.json()['id']
    resp = _delete_everyone(client, token_b, message_id)
    assert resp.status_code == 400

# ======================================================================
# source: tests/test_attachments.py
# ======================================================================
'API tests for encrypted message sending and attachment\nauthorization (upload/download from a `.bin` encrypted file).'
EMAIL_C__att = 'mallory@example.com'
def _friend_and_conversation(client, token_a, bob_id, token_b):
    """Alice sends a friend request; Bob accepts; both get a conversation."""
    resp = client.post('/api/v1/friends/request', json={'receiver_id': str(bob_id)}, headers=_auth(token_a))
    assert resp.status_code == 200, resp.text
    pending = client.get('/api/v1/friends/pending', headers=_auth(token_b)).json()
    friendship_id = pending[0]['id']
    resp = client.post('/api/v1/friends/accept', json={'friendship_id': str(friendship_id)}, headers=_auth(token_b))
    assert resp.status_code == 200, resp.text
    resp = client.post('/api/v1/conversations/private', json={'user_id': str(bob_id)}, headers=_auth(token_a))
    assert resp.status_code == 200, resp.text
    return resp.json()['id']
def test_send_encrypted_message_and_history(api_client):
    client = api_client
    (token_a, user_a) = _register(client, EMAIL_A)
    (token_b, user_b) = _register(client, EMAIL_B)
    conversation_id = _friend_and_conversation(client, token_a, user_b['id'], token_b)
    payload = {'conversation_id': str(conversation_id), 'ciphertext': 'cipher-blob', 'encrypted_key_sender': 'key-s', 'encrypted_key_receiver': 'key-r', 'nonce': 'deadbeef', 'crypto_version': 2, 'message_type': 'text', 'reply_to_id': None}
    resp = client.post('/api/v1/messages/send', json=payload, headers=_auth(token_a))
    assert resp.status_code == 200, resp.text
    message = resp.json()
    assert message['ciphertext'] == 'cipher-blob'
    resp = client.get(f'/api/v1/messages/{conversation_id}', headers=_auth(token_b))
    assert resp.status_code == 200, resp.text
    history = resp.json()
    assert len(history) == 1
    assert history[0]['sender_id'] == str(user_a['id'])
    assert history[0]['is_read'] is False
    conversations = client.get('/api/v1/conversations/', headers=_auth(token_b)).json()
    conv_b = next((c for c in conversations if c['id'] == str(conversation_id)))
    assert conv_b['unread_count'] == 1
def test_non_participant_cannot_read_history(api_client):
    client = api_client
    (token_a, _) = _register(client, EMAIL_A)
    (token_b, user_b) = _register(client, EMAIL_B)
    (token_c, _) = _register(client, EMAIL_C__att)
    conversation_id = _friend_and_conversation(client, token_a, user_b['id'], token_b)
    resp = client.get(f'/api/v1/messages/{conversation_id}', headers=_auth(token_c))
    assert resp.status_code == 400, resp.text
def _send_message(client, conversation_id, token):
    return client.post('/api/v1/messages/send', json={'conversation_id': str(conversation_id), 'ciphertext': 'payload', 'encrypted_key_sender': 'k1', 'encrypted_key_receiver': 'k2', 'nonce': 'n', 'crypto_version': 2, 'message_type': 'text', 'reply_to_id': None}, headers=_auth(token)).json()
def test_upload_download_encrypted_bin(api_client):
    client = api_client
    (token_a, _) = _register(client, EMAIL_A)
    (token_b, user_b) = _register(client, EMAIL_B)
    conversation_id = _friend_and_conversation(client, token_a, user_b['id'], token_b)
    message = _send_message(client, conversation_id, token_a)
    message_id = message['id']
    resp = client.post(f'/api/v1/attachments/upload/{message_id}', headers=_auth(token_a), files={'file': ('photo.jpg.bin', b'\x00' * 1024, 'application/octet-stream')})
    assert resp.status_code == 200, resp.text
    attachment = resp.json()['attachment']
    assert attachment['attachment_type'] == 'encrypted'
    assert attachment['size'] == 1024
    resp = client.get(f"/api/v1/attachments/{attachment['id']}", headers=_auth(token_b))
    assert resp.status_code == 200, resp.text
    assert resp.content == b'\x00' * 1024
    resp = client.get(f"/api/v1/attachments/{attachment['id']}", headers=_auth(token_a))
    assert resp.status_code == 200
def test_attachment_rejected_for_non_participant(api_client):
    client = api_client
    (token_a, _) = _register(client, EMAIL_A)
    (token_b, user_b) = _register(client, EMAIL_B)
    (token_c, _) = _register(client, EMAIL_C__att)
    conversation_id = _friend_and_conversation(client, token_a, user_b['id'], token_b)
    message = _send_message(client, conversation_id, token_a)
    upload = client.post(f"/api/v1/attachments/upload/{message['id']}", headers=_auth(token_a), files={'file': ('note.txt.bin', b'hello' * 100, 'application/octet-stream')})
    assert upload.status_code == 200, upload.text
    attachment_id = upload.json()['attachment']['id']
    resp = client.get(f'/api/v1/attachments/{attachment_id}', headers=_auth(token_c))
    assert resp.status_code == 403, resp.text
    resp = client.delete(f'/api/v1/attachments/{attachment_id}', headers=_auth(token_c))
    assert resp.status_code == 403
def test_attachment_rejects_unsupported_extension(api_client):
    client = api_client
    (token_a, _) = _register(client, EMAIL_A)
    (token_b, user_b) = _register(client, EMAIL_B)
    conversation_id = _friend_and_conversation(client, token_a, user_b['id'], token_b)
    message = _send_message(client, conversation_id, token_a)
    resp = client.post(f"/api/v1/attachments/upload/{message['id']}", headers=_auth(token_a), files={'file': ('evil.exe', b'MZ' * 512, 'application/x-msdownload')})
    assert resp.status_code == 400, resp.text
def test_attachment_rejects_disguised_script(api_client):
    client = api_client
    (token_a, _) = _register(client, EMAIL_A)
    (token_b, user_b) = _register(client, EMAIL_B)
    conversation_id = _friend_and_conversation(client, token_a, user_b['id'], token_b)
    message = _send_message(client, conversation_id, token_a)
    resp = client.post(f"/api/v1/attachments/upload/{message['id']}", headers=_auth(token_a), files={'file': ('photo.png', b'<script>alert(1)</script>', 'image/png')})
    assert resp.status_code == 400, resp.text
    assert 'does not match' in resp.json()['detail']
    resp = client.post(f"/api/v1/attachments/upload/{message['id']}", headers=_auth(token_a), files={'file': ('report.pdf', b'MZ\x90\x00' + b'\x00' * 64, 'application/pdf')})
    assert resp.status_code == 400, resp.text
    resp = client.post(f"/api/v1/attachments/upload/{message['id']}", headers=_auth(token_a), files={'file': ('report.pdf', b'%PDF-1.7\n' + b'0' * 128, 'application/pdf')})
    assert resp.status_code == 200, resp.text
    huge = client.post(f"/api/v1/attachments/upload/{message['id']}", headers=_auth(token_a), files={'file': ('big.bin', b'\x00' * (500 * 1024 * 1024 + 1), 'application/octet-stream')})
    assert huge.status_code == 400, huge.text

# ======================================================================
# source: tests/test_auth_api.py
# ======================================================================
'API integration tests for OTP auth, refresh rotation and\nrate limiting.'
EMAIL = 'alice@example.com'
class EmailRecorder__auth:
    """Captures OTPs instead of hitting SMTP."""
    sent: list[dict] = []

    @classmethod
    async def send_otp_email(cls, recipient_email: str, otp: str, **kwargs):
        cls.sent.append({'email': recipient_email, 'otp': otp})
@pytest.fixture
def auth_client(monkeypatch):
    """TestClient against an in-memory DB, SMTP replaced by a recorder."""
    monkeypatch.setattr(email_module.EmailService, 'send_otp_email', EmailRecorder__auth.send_otp_email)
    EmailRecorder__auth.sent = []
    reset_limiter()
    engine = create_async_engine('sqlite+aiosqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    TestingSessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

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
def _request_otp(client, email=EMAIL):
    resp = client.post('/api/v1/auth/send-otp', json={'email': email})
    assert resp.status_code == 200, resp.text
    return EmailRecorder__auth.sent[-1]['otp']
def _verify_otp(client, email=EMAIL, otp='123456'):
    return client.post('/api/v1/auth/verify-otp', json={'email': email, 'otp': otp})
def test_send_and_verify_otp(auth_client):
    client = auth_client
    otp = _request_otp(client)
    resp = _verify_otp(client, otp=otp)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body['access_token']
    assert body['refresh_token']
    assert body['user']['email'] == EMAIL
    set_cookie = resp.headers.get('set-cookie', '')
    assert 'cc_refresh=' in set_cookie
    assert 'HttpOnly' in set_cookie
def test_verify_wrong_otp_exhausts_attempts(auth_client):
    _request_otp(auth_client)
    for _ in range(5):
        resp = _verify_otp(auth_client, otp='000000')
        assert resp.status_code == 400
    resp = _verify_otp(auth_client, otp='000000')
    assert resp.status_code == 400
def test_verify_used_otp_rejected(auth_client):
    otp = _request_otp(auth_client)
    assert _verify_otp(auth_client, otp=otp).status_code == 200
    assert _verify_otp(auth_client, otp=otp).status_code == 400
def test_refresh_rotates_token(auth_client):
    client = auth_client
    otp = _request_otp(client)
    refresh_token = _verify_otp(client, otp=otp).json()['refresh_token']
    resp = client.post('/api/v1/auth/refresh', json={'refresh_token': refresh_token})
    assert resp.status_code == 200, resp.text
    new_refresh = resp.json()['refresh_token']
    assert new_refresh != refresh_token
    client.cookies.clear()
    resp = client.post('/api/v1/auth/refresh', json={'refresh_token': refresh_token})
    assert resp.status_code == 401
def test_reuse_after_rotation_revokes_family(auth_client):
    client = auth_client
    otp = _request_otp(client)
    refresh_token = _verify_otp(client, otp=otp).json()['refresh_token']
    resp = client.post('/api/v1/auth/refresh', json={'refresh_token': refresh_token})
    new_refresh = resp.json()['refresh_token']
    client.cookies.clear()
    client.post('/api/v1/auth/refresh', json={'refresh_token': refresh_token})
    resp = client.post('/api/v1/auth/refresh', json={'refresh_token': new_refresh})
    assert resp.status_code == 401
def test_logout_revokes_family(auth_client):
    client = auth_client
    otp = _request_otp(client)
    refresh = _verify_otp(client, otp=otp).json()['refresh_token']
    resp = client.post('/api/v1/auth/logout', json={'refresh_token': refresh})
    assert resp.status_code == 200
    resp = client.post('/api/v1/auth/refresh', json={'refresh_token': refresh})
    assert resp.status_code == 401
def test_refresh_without_token_401(auth_client):
    resp = auth_client.post('/api/v1/auth/refresh', json={})
    assert resp.status_code == 401
def test_send_otp_rate_limited_per_email(auth_client):
    client = auth_client
    for _ in range(3):
        resp = client.post('/api/v1/auth/send-otp', json={'email': 'bob@example.com'})
        assert resp.status_code == 200, resp.text
    resp = client.post('/api/v1/auth/send-otp', json={'email': 'bob@example.com'})
    assert resp.status_code == 429

# ======================================================================
# source: tests/test_blocks.py
# ======================================================================
'API tests for blocks and privacy settings.\n\nBlocking is WhatsApp-style: blocked users cannot message, call,\nsee presence, stories or avatars of the blocker, and the blocker\nstops seeing theirs too. Blocking auto-removes the friendship.\nPrivacy settings control last-seen/photo/story visibility.\n'
def _dm(client, token_a, bob_id, token_b):
    _friend(client, token_a, bob_id, token_b)
    resp = client.post('/api/v1/conversations/private', json={'user_id': str(bob_id)}, headers=_auth(token_a))
    assert resp.status_code == 200, resp.text
    return resp.json()['id']
def _block(client, token, user_id):
    resp = client.post('/api/v1/blocks/', json={'user_id': str(user_id)}, headers=_auth(token))
    return resp
def _upload_story(client, token):
    png = b'\x89PNG\r\n\x1a\n' + b'0' * 128
    resp = client.post('/api/v1/stories/', files={'file': ('status.png', io.BytesIO(png), 'image/png')}, data={'encrypted_key_sender': 'k-sender', 'nonce': 'n'}, headers=_auth(token))
    assert resp.status_code == 200, resp.text
    return resp.json()
def _feed(client, token):
    resp = client.get('/api/v1/stories/feed', headers=_auth(token))
    assert resp.status_code == 200, resp.text
    return resp.json()
def _group_by_owner(feed, user_id):
    return next((entry for entry in feed if entry['user_id'] == str(user_id)), None)
def test_block_and_list(api_client):
    client = api_client
    (token_a, user_a) = _register(client, EMAIL_A)
    (token_b, user_b) = _register(client, EMAIL_B)
    resp = _block(client, token_a, user_b['id'])
    assert resp.status_code == 200, resp.text
    assert resp.json()['status'] == 'blocked'
    blocked = client.get('/api/v1/blocks/', headers=_auth(token_a)).json()
    assert [u['id'] for u in blocked] == [str(user_b['id'])]
    blocked_b = client.get('/api/v1/blocks/', headers=_auth(token_b)).json()
    assert blocked_b == []
def test_cannot_block_self_or_missing_user(api_client):
    client = api_client
    (token_a, user_a) = _register(client, EMAIL_A)
    (token_b, _) = _register(client, EMAIL_B)
    resp = _block(client, token_a, user_a['id'])
    assert resp.status_code == 400
    import uuid
    resp = _block(client, token_a, uuid.uuid4())
    assert resp.status_code == 400
def test_duplicate_block_rejected(api_client):
    client = api_client
    (token_a, user_a) = _register(client, EMAIL_A)
    (_, user_b) = _register(client, EMAIL_B)
    assert _block(client, token_a, user_b['id']).status_code == 200
    resp = _block(client, token_a, user_b['id'])
    assert resp.status_code == 400
def test_unblock(api_client):
    client = api_client
    (token_a, user_a) = _register(client, EMAIL_A)
    (_, user_b) = _register(client, EMAIL_B)
    _block(client, token_a, user_b['id'])
    resp = client.delete(f"/api/v1/blocks/{user_b['id']}", headers=_auth(token_a))
    assert resp.status_code == 200, resp.text
    assert resp.json()['status'] == 'unblocked'
    blocked = client.get('/api/v1/blocks/', headers=_auth(token_a)).json()
    assert blocked == []
    resp = client.delete(f"/api/v1/blocks/{user_b['id']}", headers=_auth(token_a))
    assert resp.status_code == 400
def test_blocked_user_cannot_message(api_client):
    client = api_client
    (token_a, user_a) = _register(client, EMAIL_A)
    (token_b, user_b) = _register(client, EMAIL_B)
    conversation_id = _dm(client, token_a, user_b['id'], token_b)
    _block(client, token_a, user_b['id'])
    resp = _send(client, conversation_id, token_b, 'hello?')
    assert resp.status_code == 403
    resp = _send(client, conversation_id, token_a, 'goodbye')
    assert resp.status_code == 200, resp.text
def test_unblock_restores_messaging(api_client):
    client = api_client
    (token_a, user_a) = _register(client, EMAIL_A)
    (token_b, user_b) = _register(client, EMAIL_B)
    conversation_id = _dm(client, token_a, user_b['id'], token_b)
    _block(client, token_a, user_b['id'])
    client.delete(f"/api/v1/blocks/{user_b['id']}", headers=_auth(token_a))
    resp = _send(client, conversation_id, token_b, 'back again')
    assert resp.status_code == 200, resp.text
def test_blocked_user_cannot_send_friend_request(api_client):
    client = api_client
    (token_a, user_a) = _register(client, EMAIL_A)
    (token_b, user_b) = _register(client, EMAIL_B)
    _block(client, token_a, user_b['id'])
    resp = client.post('/api/v1/friends/request', json={'receiver_id': str(user_a['id'])}, headers=_auth(token_b))
    assert resp.status_code == 400
def test_block_removes_friendship(api_client):
    client = api_client
    (token_a, user_a) = _register(client, EMAIL_A)
    (token_b, user_b) = _register(client, EMAIL_B)
    _friend(client, token_a, user_b['id'], token_b)
    friends = client.get('/api/v1/friends/', headers=_auth(token_a)).json()
    assert len(friends) == 1
    _block(client, token_a, user_b['id'])
    friends = client.get('/api/v1/friends/', headers=_auth(token_a)).json()
    assert friends == []
def test_blocked_friend_story_hidden_from_feed(api_client):
    client = api_client
    (token_a, user_a) = _register(client, EMAIL_A)
    (token_b, user_b) = _register(client, EMAIL_B)
    _friend(client, token_a, user_b['id'], token_b)
    _upload_story(client, token_a)
    _block(client, token_b, user_a['id'])
    feed = _feed(client, token_b)
    assert _group_by_owner(feed, user_a['id']) is None
def test_blocked_user_cannot_view_story_media(api_client):
    client = api_client
    (token_a, user_a) = _register(client, EMAIL_A)
    (token_b, user_b) = _register(client, EMAIL_B)
    _friend(client, token_a, user_b['id'], token_b)
    story = _upload_story(client, token_a)
    _block(client, token_a, user_b['id'])
    resp = client.get(f"/api/v1/stories/{story['id']}/media", headers=_auth(token_b))
    assert resp.status_code == 404
def test_privacy_defaults_and_update(api_client):
    client = api_client
    (token_a, user_a) = _register(client, EMAIL_A)
    resp = client.get('/api/v1/blocks/privacy', headers=_auth(token_a))
    assert resp.status_code == 200, resp.text
    defaults = resp.json()
    assert defaults == {'last_seen': 'everyone', 'profile_photo': 'everyone', 'story': 'my_contacts'}
    resp = client.patch('/api/v1/blocks/privacy', json={'last_seen': 'nobody', 'profile_photo': 'my_contacts', 'story': 'everyone'}, headers=_auth(token_a))
    assert resp.status_code == 200, resp.text
    updated = resp.json()
    assert updated['last_seen'] == 'nobody'
    assert updated['profile_photo'] == 'my_contacts'
    assert updated['story'] == 'everyone'
def test_invalid_privacy_value_rejected(api_client):
    client = api_client
    (token_a, user_a) = _register(client, EMAIL_A)
    resp = client.patch('/api/v1/blocks/privacy', json={'last_seen': 'strangers'}, headers=_auth(token_a))
    assert resp.status_code == 400
def test_story_privacy_nobody_hides_from_friends(api_client):
    client = api_client
    (token_a, user_a) = _register(client, EMAIL_A)
    (token_b, user_b) = _register(client, EMAIL_B)
    _friend(client, token_a, user_b['id'], token_b)
    _upload_story(client, token_a)
    client.patch('/api/v1/blocks/privacy', json={'story': 'nobody'}, headers=_auth(token_a))
    feed = _feed(client, token_b)
    assert _group_by_owner(feed, user_a['id']) is None
    feed = _feed(client, token_a)
    assert _group_by_owner(feed, user_a['id']) is not None
def test_story_privacy_blocks_media_access(api_client):
    client = api_client
    (token_a, user_a) = _register(client, EMAIL_A)
    (token_b, user_b) = _register(client, EMAIL_B)
    _friend(client, token_a, user_b['id'], token_b)
    story = _upload_story(client, token_a)
    client.patch('/api/v1/blocks/privacy', json={'story': 'nobody'}, headers=_auth(token_a))
    resp = client.get(f"/api/v1/stories/{story['id']}/media", headers=_auth(token_b))
    assert resp.status_code == 404
def _upload_avatar(client, token):
    png = b'\x89PNG\r\n\x1a\n' + b'0' * 256
    resp = client.post('/api/v1/users/avatar', files={'file': ('avatar.png', io.BytesIO(png), 'image/png')}, headers=_auth(token))
    assert resp.status_code == 200, resp.text
def test_avatar_privacy_my_contacts(api_client):
    client = api_client
    (token_a, user_a) = _register(client, EMAIL_A)
    (token_b, user_b) = _register(client, EMAIL_B)
    (token_c, user_c) = _register(client, EMAIL_C)
    _friend(client, token_a, user_b['id'], token_b)
    _upload_avatar(client, token_a)
    resp = client.get(f"/api/v1/users/{user_a['id']}/avatar", headers=_auth(token_c))
    assert resp.status_code == 200
    client.patch('/api/v1/blocks/privacy', json={'profile_photo': 'my_contacts'}, headers=_auth(token_a))
    resp = client.get(f"/api/v1/users/{user_a['id']}/avatar", headers=_auth(token_c))
    assert resp.status_code == 404
    resp = client.get(f"/api/v1/users/{user_a['id']}/avatar", headers=_auth(token_b))
    assert resp.status_code == 200
    client.patch('/api/v1/blocks/privacy', json={'profile_photo': 'nobody'}, headers=_auth(token_a))
    resp = client.get(f"/api/v1/users/{user_a['id']}/avatar", headers=_auth(token_b))
    assert resp.status_code == 404
def test_avatar_hidden_from_blocked_user(api_client):
    client = api_client
    (token_a, user_a) = _register(client, EMAIL_A)
    (token_b, user_b) = _register(client, EMAIL_B)
    _friend(client, token_a, user_b['id'], token_b)
    _upload_avatar(client, token_a)
    _block(client, token_a, user_b['id'])
    resp = client.get(f"/api/v1/users/{user_a['id']}/avatar", headers=_auth(token_b))
    assert resp.status_code == 404

# ======================================================================
# source: tests/test_call.py
# ======================================================================
'API tests for the WebRTC call config endpoint.\n\nThe endpoint returns ICE servers for voice/video calls: the\npublic STUN server always, plus TURN relays when configured.\nMedia itself is end-to-end encrypted client-side (insertable\nstreams), so TURN relays never see call content.\n'
EMAIL__call = 'caller@example.com'
def _register__call(client):
    client.post('/api/v1/auth/send-otp', json={'email': EMAIL__call})
    otp = EmailRecorder.sent[-1]['otp']
    resp = client.post('/api/v1/auth/verify-otp', json={'email': EMAIL__call, 'otp': otp})
    assert resp.status_code == 200, resp.text
    return resp.json()['access_token']
def test_call_config_requires_auth(api_client):
    resp = api_client.get('/api/v1/call/config')
    assert resp.status_code == 401
def test_call_config_returns_stun(api_client, monkeypatch):
    monkeypatch.setattr('app.core.config.settings.TURN_URLS', '')
    token = _register__call(api_client)
    resp = api_client.get('/api/v1/call/config', headers={'Authorization': f'Bearer {token}'})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data['e2ee_supported'] is True
    stun = [s for s in data['ice_servers'] if 'stun:' in s['urls']]
    assert stun, 'STUN server missing from ICE config'
def test_call_config_includes_turn_when_configured(api_client, monkeypatch):
    monkeypatch.setattr('app.core.config.settings.TURN_URLS', 'turn:relay.example.com:3478?transport=udp')
    monkeypatch.setattr('app.core.config.settings.TURN_USERNAME', 'caller')
    monkeypatch.setattr('app.core.config.settings.TURN_PASSWORD', 'secret')
    token = _register__call(api_client)
    resp = api_client.get('/api/v1/call/config', headers={'Authorization': f'Bearer {token}'})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    turn = [s for s in data['ice_servers'] if isinstance(s['urls'], list)]
    assert turn, 'TURN server missing from ICE config'
    assert turn[0]['username'] == 'caller'
    assert turn[0]['credential'] == 'secret'

# ======================================================================
# source: tests/test_conversation_delete.py
# ======================================================================
'API tests for two-party conversation deletion.\n\nUser 1 requests the wipe -> the OTHER participant must confirm\nbefore anything is erased. On mutual consent the server purges\nevery message, attachment (rows and physical files) and the\nconversation itself. Friendships survive.\n'
EMAIL_C__cdel = 'mallory@example.com'
def _friend_and_conversation__cdel(client, token_a, bob_id, token_b):
    resp = client.post('/api/v1/friends/request', json={'receiver_id': str(bob_id)}, headers=_auth(token_a))
    assert resp.status_code == 200, resp.text
    pending = client.get('/api/v1/friends/pending', headers=_auth(token_b)).json()
    friendship_id = pending[0]['id']
    resp = client.post('/api/v1/friends/accept', json={'friendship_id': str(friendship_id)}, headers=_auth(token_b))
    assert resp.status_code == 200, resp.text
    resp = client.post('/api/v1/conversations/private', json={'user_id': str(bob_id)}, headers=_auth(token_a))
    assert resp.status_code == 200, resp.text
    return resp.json()['id']
def _send__cdel(client, conversation_id, token, content='payload'):
    resp = client.post('/api/v1/messages/send', json={'conversation_id': str(conversation_id), 'ciphertext': content, 'encrypted_key_sender': 'k1', 'encrypted_key_receiver': 'k2', 'nonce': 'n'}, headers=_auth(token))
    assert resp.status_code == 200, resp.text
    return resp.json()
def _request_delete(client, conversation_id, token):
    return client.post(f'/api/v1/conversations/{conversation_id}/delete-request', headers=_auth(token))
def _confirm_delete(client, conversation_id, token):
    return client.post(f'/api/v1/conversations/{conversation_id}/delete-confirm', headers=_auth(token))
def _cancel_delete(client, conversation_id, token):
    return client.post(f'/api/v1/conversations/{conversation_id}/delete-cancel', headers=_auth(token))
def _conversation_ids(client, token):
    data = client.get('/api/v1/conversations/', headers=_auth(token)).json()
    return [item['id'] for item in data]
def _friend_ids(client, token):
    data = client.get('/api/v1/friends/', headers=_auth(token)).json()
    return [item.get('id') or item.get('friendship_id') for item in data]
def test_request_then_confirm_wipes_everything(api_client):
    client = api_client
    (token_a, user_a) = _register(client, EMAIL_A)
    (token_b, user_b) = _register(client, EMAIL_B)
    conv = _friend_and_conversation__cdel(client, token_a, user_b['id'], token_b)
    _send__cdel(client, conv, token_a, 'hello bob')
    _send__cdel(client, conv, token_b, 'hello alice')
    resp = _request_delete(client, conv, token_a)
    assert resp.status_code == 200, resp.text
    assert resp.json()['status'] == 'requested'
    assert resp.json()['delete_requested_by'] == user_a['id']
    assert conv in _conversation_ids(client, token_a)
    assert conv in _conversation_ids(client, token_b)
    hist = client.get(f'/api/v1/messages/{conv}', headers=_auth(token_a)).json()
    assert len(hist) == 2
    resp = _confirm_delete(client, conv, token_b)
    assert resp.status_code == 200, resp.text
    assert resp.json()['status'] == 'deleted'
    assert conv not in _conversation_ids(client, token_a)
    assert conv not in _conversation_ids(client, token_b)
    hist = client.get(f'/api/v1/messages/{conv}', headers=_auth(token_a))
    assert hist.status_code in (400, 404)
def test_friendship_survives_conversation_delete(api_client):
    client = api_client
    (token_a, user_a) = _register(client, EMAIL_A)
    (token_b, user_b) = _register(client, EMAIL_B)
    conv = _friend_and_conversation__cdel(client, token_a, user_b['id'], token_b)
    _send__cdel(client, conv, token_a, 'hi')
    _request_delete(client, conv, token_a)
    _confirm_delete(client, conv, token_b)
    assert len(_friend_ids(client, token_a)) == 1
    assert len(_friend_ids(client, token_b)) == 1
def test_mutual_simultaneous_requests_delete_immediately(api_client):
    client = api_client
    (token_a, user_a) = _register(client, EMAIL_A)
    (token_b, user_b) = _register(client, EMAIL_B)
    conv = _friend_and_conversation__cdel(client, token_a, user_b['id'], token_b)
    _send__cdel(client, conv, token_a, 'hi')
    resp = _request_delete(client, conv, token_a)
    assert resp.json()['status'] == 'requested'
    resp = _request_delete(client, conv, token_b)
    assert resp.status_code == 200, resp.text
    assert resp.json()['status'] == 'deleted'
    assert conv not in _conversation_ids(client, token_a)
    assert conv not in _conversation_ids(client, token_b)
def test_duplicate_request_is_idempotent(api_client):
    client = api_client
    (token_a, user_a) = _register(client, EMAIL_A)
    (token_b, user_b) = _register(client, EMAIL_B)
    conv = _friend_and_conversation__cdel(client, token_a, user_b['id'], token_b)
    resp = _request_delete(client, conv, token_a)
    assert resp.json()['status'] == 'requested'
    resp = _request_delete(client, conv, token_a)
    assert resp.status_code == 200, resp.text
    assert resp.json()['status'] == 'requested'
    assert resp.json()['delete_requested_by'] == user_a['id']
def test_confirm_without_pending_request_is_rejected(api_client):
    client = api_client
    (token_a, user_a) = _register(client, EMAIL_A)
    (token_b, user_b) = _register(client, EMAIL_B)
    conv = _friend_and_conversation__cdel(client, token_a, user_b['id'], token_b)
    resp = _confirm_delete(client, conv, token_b)
    assert resp.status_code == 400
    assert conv in _conversation_ids(client, token_a)
def test_requester_cannot_self_confirm(api_client):
    client = api_client
    (token_a, user_a) = _register(client, EMAIL_A)
    (token_b, user_b) = _register(client, EMAIL_B)
    conv = _friend_and_conversation__cdel(client, token_a, user_b['id'], token_b)
    _request_delete(client, conv, token_a)
    resp = _confirm_delete(client, conv, token_a)
    assert resp.status_code == 400
    resp = _cancel_delete(client, conv, token_a)
    assert resp.status_code == 200
    assert resp.json()['status'] == 'cancelled'
    resp = _confirm_delete(client, conv, token_b)
    assert resp.status_code == 400
def test_other_user_can_cancel_pending_request(api_client):
    client = api_client
    (token_a, user_a) = _register(client, EMAIL_A)
    (token_b, user_b) = _register(client, EMAIL_B)
    conv = _friend_and_conversation__cdel(client, token_a, user_b['id'], token_b)
    _request_delete(client, conv, token_a)
    resp = _cancel_delete(client, conv, token_b)
    assert resp.status_code == 200
    assert resp.json()['status'] == 'cancelled'
    listed = client.get('/api/v1/conversations/', headers=_auth(token_a)).json()
    item = next((item for item in listed if item['id'] == conv))
    assert item['delete_requested_by'] is None
def test_non_participant_cannot_request(api_client):
    client = api_client
    (token_a, user_a) = _register(client, EMAIL_A)
    (token_b, user_b) = _register(client, EMAIL_B)
    (token_c, user_c) = _register(client, EMAIL_C__cdel)
    conv = _friend_and_conversation__cdel(client, token_a, user_b['id'], token_b)
    resp = _request_delete(client, conv, token_c)
    assert resp.status_code == 403
    resp = _confirm_delete(client, conv, token_c)
    assert resp.status_code == 403
    conv_c = client.post('/api/v1/conversations/private', json={'user_id': str(user_c['id'])}, headers=_auth(token_a))
    assert conv_c.status_code == 200
    conv_c_id = conv_c.json()['id']
    _send__cdel(client, conv_c_id, token_a, 'c only')
    _request_delete(client, conv_c_id, token_a)
    _confirm_delete(client, conv_c_id, token_c)
    assert conv_c_id not in _conversation_ids(client, token_a)
def test_delete_purges_attachment_rows_and_files(api_client):
    client = api_client
    (token_a, user_a) = _register(client, EMAIL_A)
    (token_b, user_b) = _register(client, EMAIL_B)
    conv = _friend_and_conversation__cdel(client, token_a, user_b['id'], token_b)
    message = _send__cdel(client, conv, token_a, 'with a file')
    resp = client.post(f"/api/v1/attachments/upload/{message['id']}", files={'file': ('pic.jpg', b'\xff\xd8\xff\xe0fake-jpeg-data', 'image/jpeg')}, headers=_auth(token_a))
    assert resp.status_code == 200, resp.text
    storage_path = resp.json()['attachment']['storage_path']
    attachment_id = str(resp.json()['attachment']['id'])
    file_path = Path(storage_path)
    assert file_path.exists()
    _request_delete(client, conv, token_a)
    _confirm_delete(client, conv, token_b)
    assert not file_path.exists()
    resp = client.get(f'/api/v1/attachments/{attachment_id}', headers=_auth(token_b))
    assert resp.status_code == 404

# ======================================================================
# source: tests/test_conversation_settings.py
# ======================================================================
'API tests for conversation pin / archive / mute settings.'
EMAIL_C__cset = 'mallory@example.com'
def _friend_and_conversation__cset(client, token_a, bob_id, token_b):
    resp = client.post('/api/v1/friends/request', json={'receiver_id': str(bob_id)}, headers=_auth(token_a))
    assert resp.status_code == 200, resp.text
    pending = client.get('/api/v1/friends/pending', headers=_auth(token_b)).json()
    friendship_id = pending[0]['id']
    resp = client.post('/api/v1/friends/accept', json={'friendship_id': str(friendship_id)}, headers=_auth(token_b))
    assert resp.status_code == 200, resp.text
    resp = client.post('/api/v1/conversations/private', json={'user_id': str(bob_id)}, headers=_auth(token_a))
    assert resp.status_code == 200, resp.text
    return resp.json()['id']
def _second_conversation(client, token_a, mallory_id, token_b):
    resp = client.post('/api/v1/friends/request', json={'receiver_id': str(mallory_id)}, headers=_auth(token_a))
    assert resp.status_code == 200, resp.text
    pending = client.get('/api/v1/friends/pending', headers=_auth(token_b)).json()
    friendship_id = pending[0]['id']
    resp = client.post('/api/v1/friends/accept', json={'friendship_id': str(friendship_id)}, headers=_auth(token_b))
    assert resp.status_code == 200, resp.text
    resp = client.post('/api/v1/conversations/private', json={'user_id': str(mallory_id)}, headers=_auth(token_a))
    assert resp.status_code == 200, resp.text
    return resp.json()['id']
def _send__cset(client, conversation_id, token, content='payload'):
    resp = client.post('/api/v1/messages/send', json={'conversation_id': str(conversation_id), 'ciphertext': content, 'encrypted_key_sender': 'k1', 'encrypted_key_receiver': 'k2', 'nonce': 'n'}, headers=_auth(token))
    assert resp.status_code == 200, resp.text
    return resp.json()
def test_pin_and_unpin_conversation(api_client):
    client = api_client
    (token_a, _) = _register(client, EMAIL_A)
    (token_b, user_b) = _register(client, EMAIL_B)
    (token_c, user_c) = _register(client, EMAIL_C__cset)
    conv_b = _friend_and_conversation__cset(client, token_a, user_b['id'], token_b)
    time.sleep(1.1)
    conv_c = _second_conversation(client, token_a, user_c['id'], token_c)
    _send__cset(client, conv_c, token_a, 'newest')
    resp = client.patch(f'/api/v1/conversations/{conv_b}', json={'is_pinned': True}, headers=_auth(token_a))
    assert resp.status_code == 200, resp.text
    assert resp.json()['is_pinned'] is True
    conversations = client.get('/api/v1/conversations/', headers=_auth(token_a)).json()
    assert conversations[0]['id'] == conv_b
    assert conversations[0]['is_pinned'] is True
    resp = client.patch(f'/api/v1/conversations/{conv_b}', json={'is_pinned': False}, headers=_auth(token_a))
    assert resp.status_code == 200, resp.text
    assert resp.json()['is_pinned'] is False
    conversations = client.get('/api/v1/conversations/', headers=_auth(token_a)).json()
    assert conversations[0]['id'] == conv_c
def test_pin_settings_are_per_user(api_client):
    client = api_client
    (token_a, _) = _register(client, EMAIL_A)
    (token_b, user_b) = _register(client, EMAIL_B)
    conv = _friend_and_conversation__cset(client, token_a, user_b['id'], token_b)
    resp = client.patch(f'/api/v1/conversations/{conv}', json={'is_pinned': True}, headers=_auth(token_a))
    assert resp.status_code == 200
    conversations = client.get('/api/v1/conversations/', headers=_auth(token_b)).json()
    assert conversations[0]['is_pinned'] is False
def test_archive_flags_conversation(api_client):
    client = api_client
    (token_a, _) = _register(client, EMAIL_A)
    (token_b, user_b) = _register(client, EMAIL_B)
    conv = _friend_and_conversation__cset(client, token_a, user_b['id'], token_b)
    resp = client.patch(f'/api/v1/conversations/{conv}', json={'is_archived': True}, headers=_auth(token_a))
    assert resp.status_code == 200, resp.text
    assert resp.json()['is_archived'] is True
    conversations = client.get('/api/v1/conversations/', headers=_auth(token_a)).json()
    assert conversations[0]['is_archived'] is True
def test_mute_until_future_is_muted(api_client):
    client = api_client
    (token_a, _) = _register(client, EMAIL_A)
    (token_b, user_b) = _register(client, EMAIL_B)
    conv = _friend_and_conversation__cset(client, token_a, user_b['id'], token_b)
    future = datetime.now(timezone.utc) + timedelta(hours=8)
    resp = client.patch(f'/api/v1/conversations/{conv}', json={'muted_until': future.isoformat()}, headers=_auth(token_a))
    assert resp.status_code == 200, resp.text
    assert resp.json()['muted'] is True
def test_mute_until_past_is_not_muted(api_client):
    client = api_client
    (token_a, _) = _register(client, EMAIL_A)
    (token_b, user_b) = _register(client, EMAIL_B)
    conv = _friend_and_conversation__cset(client, token_a, user_b['id'], token_b)
    past = datetime.now(timezone.utc) - timedelta(hours=8)
    resp = client.patch(f'/api/v1/conversations/{conv}', json={'muted_until': past.isoformat()}, headers=_auth(token_a))
    assert resp.status_code == 200, resp.text
    assert resp.json()['muted'] is False
def test_unmute_clears_mute(api_client):
    client = api_client
    (token_a, _) = _register(client, EMAIL_A)
    (token_b, user_b) = _register(client, EMAIL_B)
    conv = _friend_and_conversation__cset(client, token_a, user_b['id'], token_b)
    future = datetime.now(timezone.utc) + timedelta(hours=8)
    client.patch(f'/api/v1/conversations/{conv}', json={'muted_until': future.isoformat()}, headers=_auth(token_a))
    resp = client.patch(f'/api/v1/conversations/{conv}', json={'muted_until': None}, headers=_auth(token_a))
    assert resp.status_code == 200, resp.text
    assert resp.json()['muted'] is False
def test_non_participant_cannot_update_settings(api_client):
    client = api_client
    (token_a, _) = _register(client, EMAIL_A)
    (token_b, user_b) = _register(client, EMAIL_B)
    (token_c, _) = _register(client, EMAIL_C__cset)
    conv = _friend_and_conversation__cset(client, token_a, user_b['id'], token_b)
    resp = client.patch(f'/api/v1/conversations/{conv}', json={'is_pinned': True}, headers=_auth(token_c))
    assert resp.status_code == 403, resp.text
def test_invalid_conversation_id_rejected(api_client):
    client = api_client
    (token_a, _) = _register(client, EMAIL_A)
    resp = client.patch('/api/v1/conversations/not-a-uuid', json={'is_pinned': True}, headers=_auth(token_a))
    assert resp.status_code == 400, resp.text

# ======================================================================
# source: tests/test_device_api.py
# ======================================================================
'API integration tests for the devices / key-bundle endpoints.'
def _fernet_key() -> str:
    return Fernet.generate_key().decode()
@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(encryption_service_module.settings, 'MASTER_KEY', _fernet_key())
    engine = create_async_engine('sqlite+aiosqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    TestingSessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    async def override_get_db():
        async with TestingSessionLocal() as session:
            yield session

    async def override_get_current_user():
        async with TestingSessionLocal() as session:
            return await session.get(User, _USER_ID)

    async def setup():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with TestingSessionLocal() as session:
            session.add(User(id=_USER_ID, email='alice@example.com', username='alice', display_name='Alice'))
            await session.commit()
    import asyncio
    asyncio.run(setup())
    app_instance.dependency_overrides[get_db] = override_get_db
    app_instance.dependency_overrides[get_current_user] = override_get_current_user
    with TestClient(app_instance) as test_client:
        yield test_client
    app_instance.dependency_overrides.clear()
_USER_ID = uuid.UUID('abcdef12-3456-7890-abcd-ef1234567890')
def make_key_material(client_store_password: bytes=b'pass', opk_count: int=3) -> dict:
    """Simulate client-side generation of Signal identity/prekeys."""
    (identity_priv, identity_pub) = generate_ed25519_keypair()
    identity_x25519 = derive_x25519_from_ed25519(identity_priv)
    identity_x25519_pub = identity_x25519.public_key()
    (spk_priv, spk_pub) = generate_x25519_keypair()
    spk_pub_bytes = x25519_public_to_bytes(spk_pub)
    signature = ed25519_sign(identity_priv, spk_pub_bytes)
    opks = []
    for kid in range(1, opk_count + 1):
        (p, q) = generate_x25519_keypair()
        opks.append({'key_id': kid, 'public_key': b64encode(x25519_public_to_bytes(q))})
    return {'identity_key_public': b64encode(ed25519_public_to_bytes(identity_pub)), 'identity_key_x25519': b64encode(x25519_public_to_bytes(identity_x25519_pub)), 'signed_prekey_public': b64encode(spk_pub_bytes), 'signed_prekey_id': 1, 'signed_prekey_signature': b64encode(signature), 'one_time_prekeys': opks}
def test_register_device_primary(client):
    resp = client.post('/api/v1/devices/register', json={'device_id': str(uuid.uuid4()), 'platform': 'web', 'device_name': "Alice's Laptop", **make_key_material()})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body['success'] is True
    assert body['is_primary'] is True
def test_register_second_device_not_primary(client):
    km = make_key_material()
    resp = client.post('/api/v1/devices/register', json={'device_id': str(uuid.uuid4()), 'platform': 'web', 'device_name': 'Primary', **km})
    assert resp.status_code == 200, resp.text
    assert resp.json()['is_primary'] is True
    resp2 = client.post('/api/v1/devices/register', json={'device_id': str(uuid.uuid4()), 'platform': 'ios', 'device_name': 'iPhone', **make_key_material()})
    assert resp2.status_code == 200, resp2.text
    assert resp2.json()['is_primary'] is False
def test_get_key_bundle(client):
    client.post('/api/v1/devices/register', json={'device_id': str(uuid.uuid4()), **make_key_material()})
    resp = client.get(f'/api/v1/devices/{_USER_ID}/bundle')
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body['user_id'] == str(_USER_ID)
    assert len(body['devices']) == 1
    device = body['devices'][0]
    assert device['identity_key']
    assert device['x25519_identity_key']
    assert device['signed_prekey']['signature']
    assert len(device['one_time_prekeys']) == 1
def test_get_bundle_unknown_user_404(client):
    resp = client.get(f'/api/v1/devices/{uuid.uuid4()}/bundle')
    assert resp.status_code == 404
def test_one_time_prekeys_are_single_use(client):
    device_id = str(uuid.uuid4())
    client.post('/api/v1/devices/register', json={'device_id': device_id, **make_key_material(opk_count=2)})

    def served_opk_ids():
        resp = client.get(f'/api/v1/devices/{_USER_ID}/bundle')
        assert resp.status_code == 200, resp.text
        return [opk['key_id'] for d in resp.json()['devices'] for opk in d['one_time_prekeys']]
    first = served_opk_ids()
    second = served_opk_ids()
    assert len(first) == 1
    assert len(second) == 1
    assert first != second
    assert served_opk_ids() == []
def test_upload_prekeys(client):
    device_id = str(uuid.uuid4())
    client.post('/api/v1/devices/register', json={'device_id': device_id, **make_key_material(opk_count=0)})
    batch = make_key_material(opk_count=5)['one_time_prekeys']
    resp = client.post('/api/v1/devices/prekeys/upload', json={'device_id': device_id, 'one_time_prekeys': batch})
    assert resp.status_code == 200, resp.text
    assert len(resp.json()['one_time_prekeys']) == 5
    bundle = client.get(f'/api/v1/devices/{_USER_ID}/bundle').json()
    served = bundle['devices'][0]['one_time_prekeys']
    assert len((used := [k for k in batch if k['key_id'] == served[0]['key_id']])) == 1
    resp2 = client.post('/api/v1/devices/prekeys/upload', json={'device_id': device_id, 'one_time_prekeys': batch})
    assert resp2.status_code == 200, resp2.text
    assert len(resp2.json()['one_time_prekeys']) == 0
def test_upload_prekeys_unknown_device_404(client):
    resp = client.post('/api/v1/devices/prekeys/upload', json={'device_id': 'no-such-device', 'one_time_prekeys': make_key_material(opk_count=2)['one_time_prekeys']})
    assert resp.status_code == 404
def test_list_devices(client):
    client.post('/api/v1/devices/register', json={'device_id': 'dev-0001', 'device_name': 'Primary', **make_key_material()})
    client.post('/api/v1/devices/register', json={'device_id': 'dev-0002', 'device_name': 'Secondary', **make_key_material()})
    resp = client.get('/api/v1/devices/me')
    assert resp.status_code == 200, resp.text
    devices = resp.json()['devices']
    assert len(devices) == 2
    assert any((d['is_primary'] for d in devices))
def test_remove_secondary_device(client):
    client.post('/api/v1/devices/register', json={'device_id': 'dev-0001', **make_key_material()})
    client.post('/api/v1/devices/register', json={'device_id': 'dev-0002', **make_key_material()})
    resp = client.delete('/api/v1/devices/dev-0002')
    assert resp.status_code == 200, resp.text
    assert resp.json()['success'] is True
    remaining = client.get('/api/v1/devices/me').json()['devices']
    assert len(remaining) == 1
def test_cannot_remove_primary(client):
    client.post('/api/v1/devices/register', json={'device_id': 'dev-0001', **make_key_material()})
    resp = client.delete('/api/v1/devices/dev-0001')
    assert resp.status_code == 400
def test_remove_device_clears_its_prekeys(client):
    client.post('/api/v1/devices/register', json={'device_id': 'dev-0001', **make_key_material(opk_count=3)})
    client.post('/api/v1/devices/register', json={'device_id': 'dev-0002', **make_key_material(opk_count=3)})
    resp = client.delete('/api/v1/devices/dev-0002')
    assert resp.status_code == 200, resp.text
    bundle = client.get(f'/api/v1/devices/{_USER_ID}/bundle').json()
    assert [d['device_id'] for d in bundle['devices']] == ['dev-0001']
    resp = client.post('/api/v1/devices/register', json={'device_id': 'dev-0002', **make_key_material(opk_count=1)})
    assert resp.status_code == 200, resp.text
    bundle = client.get(f'/api/v1/devices/{_USER_ID}/bundle').json()
    dev2 = next((d for d in bundle['devices'] if d['device_id'] == 'dev-0002'))
    assert len(dev2['one_time_prekeys']) == 1

# ======================================================================
# source: tests/test_disappearing_messages.py
# ======================================================================
'API tests for disappearing messages (conversation timer + expiry purge).'
def _friend_and_conversation__disp(client, token_a, bob_id, token_b):
    resp = client.post('/api/v1/friends/request', json={'receiver_id': str(bob_id)}, headers=_auth(token_a))
    assert resp.status_code == 200, resp.text
    pending = client.get('/api/v1/friends/pending', headers=_auth(token_b)).json()
    friendship_id = pending[0]['id']
    resp = client.post('/api/v1/friends/accept', json={'friendship_id': str(friendship_id)}, headers=_auth(token_b))
    assert resp.status_code == 200, resp.text
    resp = client.post('/api/v1/conversations/private', json={'user_id': str(bob_id)}, headers=_auth(token_a))
    assert resp.status_code == 200, resp.text
    return resp.json()['id']
def _send__disp(client, conversation_id, token, content='payload'):
    resp = client.post('/api/v1/messages/send', json={'conversation_id': str(conversation_id), 'ciphertext': content, 'encrypted_key_sender': 'k1', 'encrypted_key_receiver': 'k2', 'nonce': 'n'}, headers=_auth(token))
    assert resp.status_code == 200, resp.text
    return resp.json()
def test_default_timer_is_off(api_client):
    client = api_client
    (token_a, _) = _register(client, EMAIL_A)
    (token_b, user_b) = _register(client, EMAIL_B)
    conv = _friend_and_conversation__disp(client, token_a, user_b['id'], token_b)
    conversations = client.get('/api/v1/conversations/', headers=_auth(token_a)).json()
    assert conversations[0]['disappear_after_seconds'] is None
def test_set_timer_shared_by_both_participants(api_client):
    client = api_client
    (token_a, _) = _register(client, EMAIL_A)
    (token_b, user_b) = _register(client, EMAIL_B)
    conv = _friend_and_conversation__disp(client, token_a, user_b['id'], token_b)
    resp = client.patch(f'/api/v1/conversations/{conv}', json={'disappear_after_seconds': 24 * 60 * 60}, headers=_auth(token_a))
    assert resp.status_code == 200, resp.text
    assert resp.json()['disappear_after_seconds'] == 86400
    conversations = client.get('/api/v1/conversations/', headers=_auth(token_b)).json()
    assert conversations[0]['disappear_after_seconds'] == 86400
    conversations = client.get('/api/v1/conversations/', headers=_auth(token_a)).json()
    assert conversations[0]['disappear_after_seconds'] == 86400
def test_disable_timer(api_client):
    client = api_client
    (token_a, _) = _register(client, EMAIL_A)
    (token_b, user_b) = _register(client, EMAIL_B)
    conv = _friend_and_conversation__disp(client, token_a, user_b['id'], token_b)
    client.patch(f'/api/v1/conversations/{conv}', json={'disappear_after_seconds': 3600}, headers=_auth(token_a))
    resp = client.patch(f'/api/v1/conversations/{conv}', json={'disappear_after_seconds': None}, headers=_auth(token_a))
    assert resp.status_code == 200, resp.text
    assert resp.json()['disappear_after_seconds'] is None
def test_messages_receive_expires_at_when_timer_on(api_client):
    client = api_client
    (token_a, _) = _register(client, EMAIL_A)
    (token_b, user_b) = _register(client, EMAIL_B)
    conv = _friend_and_conversation__disp(client, token_a, user_b['id'], token_b)
    message = _send__disp(client, conv, token_a, 'persistent-msg')
    assert message['expires_at'] is None
    client.patch(f'/api/v1/conversations/{conv}', json={'disappear_after_seconds': 3600}, headers=_auth(token_a))
    message = _send__disp(client, conv, token_a, 'vanishing-msg')
    assert message['expires_at'] is not None
    for token in (token_a, token_b):
        history = client.get(f'/api/v1/messages/{conv}', headers=_auth(token)).json()
        assert len(history) == 2
        assert history[0]['expires_at'] is None
        assert history[1]['expires_at'] is not None
def test_expired_message_is_purged_from_history(api_client):
    client = api_client
    (token_a, _) = _register(client, EMAIL_A)
    (token_b, user_b) = _register(client, EMAIL_B)
    conv = _friend_and_conversation__disp(client, token_a, user_b['id'], token_b)
    _send__disp(client, conv, token_a, 'persistent-msg')
    client.patch(f'/api/v1/conversations/{conv}', json={'disappear_after_seconds': 1}, headers=_auth(token_a))
    message = _send__disp(client, conv, token_a, 'vanishing-msg')
    import time as _time
    _time.sleep(1.2)
    history = client.get(f'/api/v1/messages/{conv}', headers=_auth(token_b)).json()
    assert len(history) == 1
    assert history[0]['ciphertext'] == 'persistent-msg'
    assert history[0]['id'] != message['id']
def test_expired_message_not_in_conversation_preview(api_client):
    client = api_client
    (token_a, _) = _register(client, EMAIL_A)
    (token_b, user_b) = _register(client, EMAIL_B)
    conv = _friend_and_conversation__disp(client, token_a, user_b['id'], token_b)
    client.patch(f'/api/v1/conversations/{conv}', json={'disappear_after_seconds': 1}, headers=_auth(token_a))
    _send__disp(client, conv, token_a, 'vanishing-last-msg')
    import time as _time
    _time.sleep(1.2)
    conversations = client.get('/api/v1/conversations/', headers=_auth(token_a)).json()
    item = next((c for c in conversations if c['id'] == conv))
    assert item['last_message'] is None
    assert item['unread_count'] == 0
def test_expired_message_cannot_be_replied_to(api_client):
    client = api_client
    (token_a, _) = _register(client, EMAIL_A)
    (token_b, user_b) = _register(client, EMAIL_B)
    conv = _friend_and_conversation__disp(client, token_a, user_b['id'], token_b)
    client.patch(f'/api/v1/conversations/{conv}', json={'disappear_after_seconds': 1}, headers=_auth(token_a))
    message = _send__disp(client, conv, token_a, 'vanishing-msg')
    import time as _time
    _time.sleep(1.2)
    resp = client.post('/api/v1/messages/send', json={'conversation_id': str(conv), 'ciphertext': 'reply', 'encrypted_key_sender': 'k', 'encrypted_key_receiver': 'k', 'nonce': 'n', 'reply_to_id': str(message['id'])}, headers=_auth(token_b))
    assert resp.status_code == 400, resp.text

# ======================================================================
# source: tests/test_group_chats.py
# ======================================================================
'API tests for group chats.\n\nGroup chat E2EE: every message is encrypted with a fresh\nAES-256-GCM key wrapped per recipient (message_recipient_keys).\nThe backend only stores ciphertext + wrapped keys. The creator\nis admin; admins add members; members can leave; a group whose\nlast member leaves ceases to exist.\n'
EMAIL_D = 'dave@example.com'
def _friend_each_with(client, token_a, others):
    for (token_b, other_id) in others:
        _friend(client, token_a, other_id, token_b)
def _send_group(client, conversation_id, token, content='payload'):
    resp = client.post('/api/v1/messages/send', json={'conversation_id': str(conversation_id), 'ciphertext': content, 'encrypted_key_sender': 'k1', 'encrypted_key_receiver': 'k2', 'nonce': 'n', 'recipient_keys': [{'user_id': str(_other_member_id(client, conversation_id, token)), 'encrypted_key': 'wrapped'}]}, headers=_auth(token))
    assert resp.status_code == 200, resp.text
    return resp.json()
def _other_member_id(client, conversation_id, token):
    detail = client.get(f'/api/v1/conversations/{conversation_id}', headers=_auth(token)).json()
    return detail['participants'][0]['user_id']
def _group_detail(client, conversation_id, token):
    resp = client.get(f'/api/v1/conversations/{conversation_id}', headers=_auth(token))
    assert resp.status_code == 200, resp.text
    return resp.json()
def _conversations(client, token):
    resp = client.get('/api/v1/conversations/', headers=_auth(token))
    assert resp.status_code == 200, resp.text
    return resp.json()
def test_create_group_with_friends(api_client):
    client = api_client
    (token_a, user_a) = _register(client, EMAIL_A)
    (token_b, user_b) = _register(client, EMAIL_B)
    (token_c, user_c) = _register(client, EMAIL_C)
    _friend_each_with(client, token_a, [(token_b, user_b['id']), (token_c, user_c['id'])])
    group = _create_group(client, token_a, 'Trip', [user_b['id'], user_c['id']])
    assert group['conversation_type'] == 'group'
    assert group['name'] == 'Trip'
    assert group['participant_count'] == 3
    detail = _group_detail(client, group['id'], token_a)
    assert detail['is_admin'] is True
    by_id = {p['user_id']: p for p in detail['participants']}
    assert by_id[str(user_a['id'])]['is_admin'] is True
    assert by_id[str(user_b['id'])]['is_admin'] is False
    assert by_id[str(user_c['id'])]['is_admin'] is False
    assert group['id'] in [c['id'] for c in _conversations(client, token_a)]
    assert group['id'] in [c['id'] for c in _conversations(client, token_b)]
    assert group['id'] in [c['id'] for c in _conversations(client, token_c)]
    listed = next((c for c in _conversations(client, token_a) if c['id'] == group['id']))
    assert listed['conversation_type'] == 'group'
    assert listed['name'] == 'Trip'
    assert listed['participant_count'] == 3
    assert listed['other_user'] is None
def test_create_group_requires_friends(api_client):
    client = api_client
    (token_a, user_a) = _register(client, EMAIL_A)
    (token_b, user_b) = _register(client, EMAIL_B)
    resp = client.post('/api/v1/conversations/group', json={'name': 'Sneaky', 'member_ids': [str(user_b['id'])]}, headers=_auth(token_a))
    assert resp.status_code == 400
    assert 'friends' in resp.json()['detail']
def test_create_group_validation(api_client):
    client = api_client
    (token_a, user_a) = _register(client, EMAIL_A)
    (token_b, user_b) = _register(client, EMAIL_B)
    _friend(client, token_a, user_b['id'], token_b)
    resp = client.post('/api/v1/conversations/group', json={'name': '', 'member_ids': [str(user_b['id'])]}, headers=_auth(token_a))
    assert resp.status_code in (400, 422)
    resp = client.post('/api/v1/conversations/group', json={'name': 'Alone', 'member_ids': []}, headers=_auth(token_a))
    assert resp.status_code in (400, 422)
    resp = client.post('/api/v1/conversations/group', json={'name': 'Self', 'member_ids': [str(user_a['id'])]}, headers=_auth(token_a))
    assert resp.status_code == 400
    group = _create_group(client, token_a, 'Dup', [user_b['id'], user_b['id']])
    assert group['participant_count'] == 2
def test_group_detail_exposes_public_keys(api_client):
    client = api_client
    (token_a, user_a) = _register(client, EMAIL_A)
    (token_b, user_b) = _register(client, EMAIL_B)
    _friend(client, token_a, user_b['id'], token_b)
    group = _create_group(client, token_a, 'Keys', [user_b['id']])
    detail = _group_detail(client, group['id'], token_a)
    assert len(detail['participants']) == 2
    for p in detail['participants']:
        assert 'display_name' in p
        assert 'username' in p
        assert 'public_key' in p or p['public_key'] is None
def test_group_detail_rejects_non_participant(api_client):
    client = api_client
    (token_a, user_a) = _register(client, EMAIL_A)
    (token_b, user_b) = _register(client, EMAIL_B)
    (token_c, user_c) = _register(client, EMAIL_C)
    _friend_each_with(client, token_a, [(token_b, user_b['id']), (token_c, user_c['id'])])
    group = _create_group(client, token_a, 'Closed', [user_b['id']])
    resp = client.get(f"/api/v1/conversations/{group['id']}", headers=_auth(token_c))
    assert resp.status_code == 403
def test_group_detail_rejects_private_conversation(api_client):
    client = api_client
    (token_a, user_a) = _register(client, EMAIL_A)
    (token_b, user_b) = _register(client, EMAIL_B)
    _friend(client, token_a, user_b['id'], token_b)
    resp = client.post('/api/v1/conversations/private', json={'user_id': str(user_b['id'])}, headers=_auth(token_a))
    private_id = resp.json()['id']
    resp = client.get(f'/api/v1/conversations/{private_id}', headers=_auth(token_a))
    assert resp.status_code == 400
def test_group_message_stores_recipient_keys(api_client):
    client = api_client
    (token_a, user_a) = _register(client, EMAIL_A)
    (token_b, user_b) = _register(client, EMAIL_B)
    (token_c, user_c) = _register(client, EMAIL_C)
    _friend_each_with(client, token_a, [(token_b, user_b['id']), (token_c, user_c['id'])])
    group = _create_group(client, token_a, 'Triple', [user_b['id'], user_c['id']])
    message = _send_group(client, group['id'], token_a, 'hello everyone')
    assert message['recipient_keys']
    assert len(message['recipient_keys']) >= 1
    for member_token in (token_b, token_c):
        history = client.get(f"/api/v1/messages/{group['id']}", headers=_auth(member_token)).json()
        assert len(history) == 2
        text_messages = [m for m in history if m['message_type'] == 'text']
        assert len(text_messages) == 1
        assert text_messages[0]['recipient_keys']
        assert any((k['user_id'] == str(user_a['id']) for k in text_messages[0]['recipient_keys']))
def test_group_message_requires_membership(api_client):
    client = api_client
    (token_a, user_a) = _register(client, EMAIL_A)
    (token_b, user_b) = _register(client, EMAIL_B)
    (token_c, user_c) = _register(client, EMAIL_C)
    _friend_each_with(client, token_a, [(token_b, user_b['id']), (token_c, user_c['id'])])
    group = _create_group(client, token_a, 'Exclusive', [user_b['id']])
    resp = client.post('/api/v1/messages/send', json={'conversation_id': str(group['id']), 'ciphertext': 'intruder', 'encrypted_key_sender': 'k1', 'encrypted_key_receiver': 'k2', 'nonce': 'n'}, headers=_auth(token_c))
    assert resp.status_code == 400
    resp = client.get(f"/api/v1/messages/{group['id']}", headers=_auth(token_c))
    assert resp.status_code == 400
def test_admin_adds_member(api_client):
    client = api_client
    (token_a, user_a) = _register(client, EMAIL_A)
    (token_b, user_b) = _register(client, EMAIL_B)
    (token_c, user_c) = _register(client, EMAIL_C)
    (token_d, user_d) = _register(client, EMAIL_D)
    _friend_each_with(client, token_a, [(token_b, user_b['id']), (token_c, user_c['id']), (token_d, user_d['id'])])
    group = _create_group(client, token_a, 'Growing', [user_b['id']])
    resp = client.post(f"/api/v1/conversations/{group['id']}/group/add", json={'member_ids': [str(user_c['id']), str(user_d['id'])]}, headers=_auth(token_a))
    assert resp.status_code == 200, resp.text
    assert resp.json()['participant_count'] == 4
    detail = _group_detail(client, group['id'], token_c)
    assert detail['participant_count'] == 4
def test_non_admin_cannot_add_members(api_client):
    client = api_client
    (token_a, user_a) = _register(client, EMAIL_A)
    (token_b, user_b) = _register(client, EMAIL_B)
    (token_c, user_c) = _register(client, EMAIL_C)
    (token_d, user_d) = _register(client, EMAIL_D)
    _friend_each_with(client, token_a, [(token_b, user_b['id']), (token_c, user_c['id']), (token_d, user_d['id'])])
    _friend(client, token_b, user_d['id'], token_d)
    group = _create_group(client, token_a, 'Strict', [user_b['id']])
    resp = client.post(f"/api/v1/conversations/{group['id']}/group/add", json={'member_ids': [str(user_d['id'])]}, headers=_auth(token_b))
    assert resp.status_code == 403
def test_add_member_requires_friendship(api_client):
    client = api_client
    (token_a, user_a) = _register(client, EMAIL_A)
    (token_b, user_b) = _register(client, EMAIL_B)
    (token_c, user_c) = _register(client, EMAIL_C)
    _friend_each_with(client, token_a, [(token_b, user_b['id'])])
    group = _create_group(client, token_a, 'FriendsOnly', [user_b['id']])
    resp = client.post(f"/api/v1/conversations/{group['id']}/group/add", json={'member_ids': [str(user_c['id'])]}, headers=_auth(token_a))
    assert resp.status_code == 400
def test_member_leaves_group(api_client):
    client = api_client
    (token_a, user_a) = _register(client, EMAIL_A)
    (token_b, user_b) = _register(client, EMAIL_B)
    _friend(client, token_a, user_b['id'], token_b)
    group = _create_group(client, token_a, 'Two', [user_b['id']])
    resp = client.post(f"/api/v1/conversations/{group['id']}/group/leave", headers=_auth(token_b))
    assert resp.status_code == 200, resp.text
    assert resp.json()['status'] == 'left'
    detail = _group_detail(client, group['id'], token_a)
    assert detail['participant_count'] == 1
    assert str(user_b['id']) not in [p['user_id'] for p in detail['participants']]
    resp = client.get(f"/api/v1/conversations/{group['id']}", headers=_auth(token_b))
    assert resp.status_code == 403
def test_last_member_leaving_deletes_group(api_client):
    client = api_client
    (token_a, user_a) = _register(client, EMAIL_A)
    (token_b, user_b) = _register(client, EMAIL_B)
    _friend(client, token_a, user_b['id'], token_b)
    group = _create_group(client, token_a, 'Doomed', [user_b['id']])
    resp = client.post(f"/api/v1/conversations/{group['id']}/group/leave", headers=_auth(token_a))
    assert resp.status_code == 200, resp.text
    assert resp.json()['status'] == 'left'
    assert group['id'] in [c['id'] for c in _conversations(client, token_b)]
    resp = client.post(f"/api/v1/conversations/{group['id']}/group/leave", headers=_auth(token_b))
    assert resp.status_code == 200, resp.text
    assert resp.json()['status'] == 'deleted'
    assert group['id'] not in [c['id'] for c in _conversations(client, token_b)]
def test_leave_reassigns_admin_to_remaining_member(api_client):
    client = api_client
    (token_a, user_a) = _register(client, EMAIL_A)
    (token_b, user_b) = _register(client, EMAIL_B)
    (token_c, user_c) = _register(client, EMAIL_C)
    _friend_each_with(client, token_a, [(token_b, user_b['id']), (token_c, user_c['id'])])
    group = _create_group(client, token_a, 'Legacy', [user_b['id'], user_c['id']])
    resp = client.post(f"/api/v1/conversations/{group['id']}/group/leave", headers=_auth(token_a))
    assert resp.status_code == 200, resp.text
    detail = _group_detail(client, group['id'], token_b)
    by_id = {p['user_id']: p for p in detail['participants']}
    assert by_id[str(user_b['id'])]['is_admin'] is True
    assert detail['is_admin'] is True
def test_cannot_leave_private_conversation(api_client):
    client = api_client
    (token_a, user_a) = _register(client, EMAIL_A)
    (token_b, user_b) = _register(client, EMAIL_B)
    _friend(client, token_a, user_b['id'], token_b)
    resp = client.post('/api/v1/conversations/private', json={'user_id': str(user_b['id'])}, headers=_auth(token_a))
    private_id = resp.json()['id']
    resp = client.post(f'/api/v1/conversations/{private_id}/group/leave', headers=_auth(token_a))
    assert resp.status_code == 400
def test_two_party_delete_rejected_for_groups(api_client):
    client = api_client
    (token_a, user_a) = _register(client, EMAIL_A)
    (token_b, user_b) = _register(client, EMAIL_B)
    _friend(client, token_a, user_b['id'], token_b)
    group = _create_group(client, token_a, 'KeepMe', [user_b['id']])
    resp = client.post(f"/api/v1/conversations/{group['id']}/delete-request", headers=_auth(token_a))
    assert resp.status_code == 400
    assert group['id'] in [c['id'] for c in _conversations(client, token_a)]
    assert group['id'] in [c['id'] for c in _conversations(client, token_b)]
def test_stale_recipient_key_for_removed_member_rejected(api_client):
    client = api_client
    (token_a, user_a) = _register(client, EMAIL_A)
    (token_b, user_b) = _register(client, EMAIL_B)
    (token_c, user_c) = _register(client, EMAIL_C)
    _friend_each_with(client, token_a, [(token_b, user_b['id']), (token_c, user_c['id'])])
    group = _create_group(client, token_a, 'Rotate', [user_b['id'], user_c['id']])
    resp = client.post(f"/api/v1/conversations/{group['id']}/group/remove", json={'user_id': str(user_c['id'])}, headers=_auth(token_a))
    assert resp.status_code == 200, resp.text
    resp = client.post('/api/v1/messages/send', json={'conversation_id': str(group['id']), 'ciphertext': 'payload', 'encrypted_key_sender': 'k1', 'encrypted_key_receiver': 'k2', 'nonce': 'n', 'recipient_keys': [{'user_id': str(user_c['id']), 'encrypted_key': 'wrapped'}, {'user_id': str(user_b['id']), 'encrypted_key': 'wrapped'}]}, headers=_auth(token_a))
    assert resp.status_code == 400, resp.text
    assert 'Group membership changed' in resp.json()['detail']
    resp = client.get(f"/api/v1/messages/{group['id']}", headers=_auth(token_a))
    assert resp.status_code == 200
    assert all((m['ciphertext'] != 'payload' for m in resp.json()))
    resp = client.post('/api/v1/messages/send', json={'conversation_id': str(group['id']), 'ciphertext': 'payload', 'encrypted_key_sender': 'k1', 'encrypted_key_receiver': 'k2', 'nonce': 'n', 'recipient_keys': [{'user_id': str(user_b['id']), 'encrypted_key': 'wrapped'}]}, headers=_auth(token_a))
    assert resp.status_code == 200, resp.text
def test_stale_envelope_for_removed_members_device_rejected(api_client):
    client = api_client
    (token_a, user_a) = _register(client, EMAIL_A)
    (token_b, user_b) = _register(client, EMAIL_B)
    (token_c, user_c) = _register(client, EMAIL_C)
    _friend_each_with(client, token_a, [(token_b, user_b['id']), (token_c, user_c['id'])])
    group = _create_group(client, token_a, 'Envelope', [user_b['id'], user_c['id']])
    resp = client.post('/api/v1/devices/register', json={'device_id': str(uuid.uuid4()), 'identity_key_public': 'x', 'identity_key_x25519': 'x', 'signed_prekey_public': 'x', 'signed_prekey_id': 1, 'signed_prekey_signature': 'x', 'one_time_prekeys': []}, headers=_auth(token_c))
    assert resp.status_code == 200, resp.text
    stale_device_id = resp.json()['device_id']
    resp = client.post(f"/api/v1/conversations/{group['id']}/group/remove", json={'user_id': str(user_c['id'])}, headers=_auth(token_a))
    assert resp.status_code == 200, resp.text
    resp = client.post('/api/v1/messages/send', json={'conversation_id': str(group['id']), 'ciphertext': 'payload', 'encrypted_key_sender': 'k1', 'encrypted_key_receiver': 'k2', 'nonce': 'n', 'recipient_keys': [{'user_id': str(user_b['id']), 'encrypted_key': 'wrapped'}], 'envelopes': [{'device_id': stale_device_id, 'data': 'x'}]}, headers=_auth(token_a))
    assert resp.status_code == 400, resp.text
    assert 'Group membership changed' in resp.json()['detail']

# ======================================================================
# source: tests/test_group_invite_links.py
# ======================================================================
'API tests for group invite links: admin-only management,\ntoken redemption, idempotent joins, revoke + reset semantics.'
EMAIL_C__gil = 'mallory@example.com'
def _friend_and_conversation__gil(client, token_a, bob_id, token_b):
    resp = client.post('/api/v1/friends/request', json={'receiver_id': str(bob_id)}, headers=_auth(token_a))
    assert resp.status_code == 200, resp.text
    pending = client.get('/api/v1/friends/pending', headers=_auth(token_b)).json()
    friendship_id = pending[0]['id']
    resp = client.post('/api/v1/friends/accept', json={'friendship_id': str(friendship_id)}, headers=_auth(token_b))
    assert resp.status_code == 200, resp.text
    resp = client.post('/api/v1/conversations/private', json={'user_id': str(bob_id)}, headers=_auth(token_a))
    assert resp.status_code == 200, resp.text
    return resp.json()['id']
def _make_friends(client, token_a, token_b, user_b_id):
    """Both directions so either user can be added to a group."""
    _friend_and_conversation__gil(client, token_a, user_b_id, token_b)
def _create_group__gil(client, token, member_ids, name='Test Group'):
    resp = client.post('/api/v1/conversations/group', json={'name': name, 'member_ids': member_ids}, headers=_auth(token))
    assert resp.status_code == 200, resp.text
    return resp.json()
def _create_invite(client, conversation_id, token):
    resp = client.post(f'/api/v1/conversations/{conversation_id}/group/invite-link', headers=_auth(token))
    assert resp.status_code == 200, resp.text
    return resp.json()
def test_create_and_read_invite_link(api_client):
    client = api_client
    (token_a, _) = _register(client, EMAIL_A)
    (token_b, user_b) = _register(client, EMAIL_B)
    _make_friends(client, token_a, token_b, user_b['id'])
    group = _create_group__gil(client, token_a, [str(user_b['id'])])
    link = _create_invite(client, group['id'], token_a)
    assert link['token']
    assert len(link['token']) >= 32
    assert link['conversation_id'] == group['id']
    assert link['revoked'] is False
    assert link['expires_at'] is None
    read = client.get(f"/api/v1/conversations/{group['id']}/group/invite-link", headers=_auth(token_a))
    assert read.status_code == 200, read.text
    assert read.json()['token'] == link['token']
def test_invite_link_admin_only(api_client):
    client = api_client
    (token_a, _) = _register(client, EMAIL_A)
    (token_b, user_b) = _register(client, EMAIL_B)
    _make_friends(client, token_a, token_b, user_b['id'])
    group = _create_group__gil(client, token_a, [str(user_b['id'])])
    _create_invite(client, group['id'], token_a)
    for (method, path) in [('get', f"/api/v1/conversations/{group['id']}/group/invite-link"), ('post', f"/api/v1/conversations/{group['id']}/group/invite-link"), ('delete', f"/api/v1/conversations/{group['id']}/group/invite-link")]:
        resp = getattr(client, method)(path, headers=_auth(token_b))
        assert resp.status_code == 403, (method, resp.text)
    (token_c, _) = _register(client, EMAIL_C__gil)
    resp = client.post(f"/api/v1/conversations/{group['id']}/group/invite-link", headers=_auth(token_c))
    assert resp.status_code == 403, resp.text
def test_reset_invalidates_previous_link(api_client):
    client = api_client
    (token_a, _) = _register(client, EMAIL_A)
    (token_b, user_b) = _register(client, EMAIL_B)
    (token_c, user_c) = _register(client, EMAIL_C__gil)
    _make_friends(client, token_a, token_b, user_b['id'])
    _make_friends(client, token_a, token_c, user_c['id'])
    group = _create_group__gil(client, token_a, [str(user_b['id'])])
    first = _create_invite(client, group['id'], token_a)
    second = _create_invite(client, group['id'], token_a)
    assert second['token'] != first['token']
    resp = client.post('/api/v1/conversations/join-with-link', json={'token': first['token']}, headers=_auth(token_c))
    assert resp.status_code == 403, resp.text
    resp = client.post('/api/v1/conversations/join-with-link', json={'token': second['token']}, headers=_auth(token_c))
    assert resp.status_code == 200, resp.text
    assert resp.json()['status'] == 'joined'
def test_revoke_invalidates_link(api_client):
    client = api_client
    (token_a, _) = _register(client, EMAIL_A)
    (token_b, user_b) = _register(client, EMAIL_B)
    (token_c, _) = _register(client, EMAIL_C__gil)
    _make_friends(client, token_a, token_b, user_b['id'])
    group = _create_group__gil(client, token_a, [str(user_b['id'])])
    link = _create_invite(client, group['id'], token_a)
    resp = client.delete(f"/api/v1/conversations/{group['id']}/group/invite-link", headers=_auth(token_a))
    assert resp.status_code == 200, resp.text
    assert resp.json()['revoked'] is True
    read = client.get(f"/api/v1/conversations/{group['id']}/group/invite-link", headers=_auth(token_a)).json()
    assert read is None
    resp = client.post('/api/v1/conversations/join-with-link', json={'token': link['token']}, headers=_auth(token_c))
    assert resp.status_code == 403, resp.text
def test_join_with_link_adds_member(api_client):
    client = api_client
    (token_a, _) = _register(client, EMAIL_A)
    (token_b, user_b) = _register(client, EMAIL_B)
    (token_c, user_c) = _register(client, EMAIL_C__gil)
    _make_friends(client, token_a, token_b, user_b['id'])
    group = _create_group__gil(client, token_a, [str(user_b['id'])])
    link = _create_invite(client, group['id'], token_a)
    resp = client.post('/api/v1/conversations/join-with-link', json={'token': link['token']}, headers=_auth(token_c))
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data['status'] == 'joined'
    assert data['conversation_id'] == group['id']
    assert data['participant_count'] == 3
    detail = client.get(f"/api/v1/conversations/{group['id']}", headers=_auth(token_c))
    assert detail.status_code == 200, detail.text
    assert detail.json()['participant_count'] == 3
    me = next((p for p in detail.json()['participants'] if p['user_id'] == str(user_c['id'])))
    assert me['is_admin'] is False
    history = client.get(f"/api/v1/messages/{group['id']}", headers=_auth(token_a)).json()
    notices = [m['ciphertext'] for m in history if m['message_type'] == 'system']
    assert any(('joined the group' in n for n in notices))
def test_join_is_idempotent(api_client):
    client = api_client
    (token_a, _) = _register(client, EMAIL_A)
    (token_b, user_b) = _register(client, EMAIL_B)
    (token_c, user_c) = _register(client, EMAIL_C__gil)
    _make_friends(client, token_a, token_b, user_b['id'])
    group = _create_group__gil(client, token_a, [str(user_b['id'])])
    link = _create_invite(client, group['id'], token_a)
    first = client.post('/api/v1/conversations/join-with-link', json={'token': link['token']}, headers=_auth(token_c))
    assert first.status_code == 200
    assert first.json()['status'] == 'joined'
    second = client.post('/api/v1/conversations/join-with-link', json={'token': link['token']}, headers=_auth(token_c))
    assert second.status_code == 200, second.text
    assert second.json()['status'] == 'already_member'
    assert second.json()['conversation_id'] == group['id']
def test_join_with_invalid_token_rejected(api_client):
    client = api_client
    (token_a, _) = _register(client, EMAIL_A)
    (token_b, user_b) = _register(client, EMAIL_B)
    (token_c, _) = _register(client, EMAIL_C__gil)
    _make_friends(client, token_a, token_b, user_b['id'])
    _create_group__gil(client, token_a, [str(user_b['id'])])
    resp = client.post('/api/v1/conversations/join-with-link', json={'token': 'not-a-real-token'}, headers=_auth(token_c))
    assert resp.status_code == 403, resp.text
    resp = client.post('/api/v1/conversations/join-with-link', json={'token': 'https://chat.example/join/not-a-real-token'}, headers=_auth(token_c))
    assert resp.status_code == 403, resp.text
def test_join_rejects_private_conversation_links(api_client):
    """A forged token can only ever point at a group: the link
    table only stores group conversations, so this guards the
    (impossible) case where a token maps to a private chat."""
    client = api_client
    (token_a, _) = _register(client, EMAIL_A)
    (token_b, user_b) = _register(client, EMAIL_B)
    _friend_and_conversation__gil(client, token_a, user_b['id'], token_b)
    resp = client.post('/api/v1/conversations/join-with-link', json={'token': 'whatever'}, headers=_auth(token_b))
    assert resp.status_code == 403, resp.text

# ======================================================================
# source: tests/test_group_polish.py
# ======================================================================
'API tests for group chat polish.\n\nAdds: update name/description (admin only), remove member\n(admin only), promote/demote admin (admin only), group avatar\nupload/fetch, and plaintext "system" messages that record every\nmembership change in the chat history.\n'
def _history(client, conversation_id, token):
    resp = client.get(f'/api/v1/messages/{conversation_id}', headers=_auth(token))
    assert resp.status_code == 200, resp.text
    return resp.json()
def _system_texts(client, conversation_id, token):
    return [m['ciphertext'] for m in _history(client, conversation_id, token) if m['message_type'] == 'system']
def test_admin_updates_group_name_and_description(api_client):
    client = api_client
    (token_a, user_a) = _register(client, EMAIL_A)
    (token_b, user_b) = _register(client, EMAIL_B)
    _friend(client, token_a, user_b['id'], token_b)
    group = _create_group(client, token_a, 'Old Name', [user_b['id']])
    resp = client.patch(f"/api/v1/conversations/{group['id']}/group", json={'name': 'New Name', 'description': 'Road trip 2026'}, headers=_auth(token_a))
    assert resp.status_code == 200, resp.text
    assert resp.json()['name'] == 'New Name'
    assert resp.json()['description'] == 'Road trip 2026'
    detail = _group_detail(client, group['id'], token_b)
    assert detail['name'] == 'New Name'
    assert detail['description'] == 'Road trip 2026'
    texts = _system_texts(client, group['id'], token_a)
    assert any(('changed the group name' in t for t in texts))
def test_non_admin_cannot_update_group(api_client):
    client = api_client
    (token_a, user_a) = _register(client, EMAIL_A)
    (token_b, user_b) = _register(client, EMAIL_B)
    _friend(client, token_a, user_b['id'], token_b)
    group = _create_group(client, token_a, 'Locked', [user_b['id']])
    resp = client.patch(f"/api/v1/conversations/{group['id']}/group", json={'name': 'Hijacked'}, headers=_auth(token_b))
    assert resp.status_code == 403
def test_group_description_can_be_cleared(api_client):
    client = api_client
    (token_a, user_a) = _register(client, EMAIL_A)
    (token_b, user_b) = _register(client, EMAIL_B)
    _friend(client, token_a, user_b['id'], token_b)
    group = _create_group(client, token_a, 'Desc', [user_b['id']])
    client.patch(f"/api/v1/conversations/{group['id']}/group", json={'description': 'temporary'}, headers=_auth(token_a))
    resp = client.patch(f"/api/v1/conversations/{group['id']}/group", json={'description': ''}, headers=_auth(token_a))
    assert resp.status_code == 200, resp.text
    assert resp.json()['description'] is None
def test_admin_removes_member(api_client):
    client = api_client
    (token_a, user_a) = _register(client, EMAIL_A)
    (token_b, user_b) = _register(client, EMAIL_B)
    (token_c, user_c) = _register(client, EMAIL_C)
    _friend_each_with(client, token_a, [(token_b, user_b['id']), (token_c, user_c['id'])])
    group = _create_group(client, token_a, 'Purge', [user_b['id'], user_c['id']])
    resp = client.post(f"/api/v1/conversations/{group['id']}/group/remove", json={'user_id': str(user_c['id'])}, headers=_auth(token_a))
    assert resp.status_code == 200, resp.text
    assert resp.json()['status'] == 'removed'
    detail = _group_detail(client, group['id'], token_a)
    assert detail['participant_count'] == 2
    assert str(user_c['id']) not in [p['user_id'] for p in detail['participants']]
    resp = client.get(f"/api/v1/conversations/{group['id']}", headers=_auth(token_c))
    assert resp.status_code == 403
    texts = _system_texts(client, group['id'], token_a)
    assert any(('removed' in t for t in texts))
def test_non_admin_cannot_remove_member(api_client):
    client = api_client
    (token_a, user_a) = _register(client, EMAIL_A)
    (token_b, user_b) = _register(client, EMAIL_B)
    (token_c, user_c) = _register(client, EMAIL_C)
    _friend_each_with(client, token_a, [(token_b, user_b['id']), (token_c, user_c['id'])])
    _friend(client, token_b, user_c['id'], token_c)
    group = _create_group(client, token_a, 'NoTouch', [user_b['id'], user_c['id']])
    resp = client.post(f"/api/v1/conversations/{group['id']}/group/remove", json={'user_id': str(user_c['id'])}, headers=_auth(token_b))
    assert resp.status_code == 403
def test_cannot_remove_or_demote_creator(api_client):
    client = api_client
    (token_a, user_a) = _register(client, EMAIL_A)
    (token_b, user_b) = _register(client, EMAIL_B)
    _friend(client, token_a, user_b['id'], token_b)
    group = _create_group(client, token_a, 'CreatorSafe', [user_b['id']])
    resp = client.post(f"/api/v1/conversations/{group['id']}/group/admin", json={'user_id': str(user_b['id']), 'is_admin': True}, headers=_auth(token_a))
    assert resp.status_code == 200, resp.text
    resp = client.post(f"/api/v1/conversations/{group['id']}/group/remove", json={'user_id': str(user_a['id'])}, headers=_auth(token_b))
    assert resp.status_code == 400
    resp = client.post(f"/api/v1/conversations/{group['id']}/group/remove", json={'user_id': str(user_a['id'])}, headers=_auth(token_a))
    assert resp.status_code == 400
    resp = client.post(f"/api/v1/conversations/{group['id']}/group/admin", json={'user_id': str(user_a['id']), 'is_admin': False}, headers=_auth(token_b))
    assert resp.status_code == 400
def test_promote_and_demote_admin(api_client):
    client = api_client
    (token_a, user_a) = _register(client, EMAIL_A)
    (token_b, user_b) = _register(client, EMAIL_B)
    _friend(client, token_a, user_b['id'], token_b)
    group = _create_group(client, token_a, 'Hierarchy', [user_b['id']])
    resp = client.post(f"/api/v1/conversations/{group['id']}/group/admin", json={'user_id': str(user_b['id']), 'is_admin': True}, headers=_auth(token_a))
    assert resp.status_code == 200, resp.text
    assert resp.json()['is_admin'] is True
    detail = _group_detail(client, group['id'], token_b)
    by_id = {p['user_id']: p for p in detail['participants']}
    assert by_id[str(user_b['id'])]['is_admin'] is True
    texts = _system_texts(client, group['id'], token_a)
    assert any(('made' in t and 'an admin' in t for t in texts))
    resp = client.post(f"/api/v1/conversations/{group['id']}/group/admin", json={'user_id': str(user_b['id']), 'is_admin': False}, headers=_auth(token_a))
    assert resp.status_code == 200, resp.text
    assert resp.json()['is_admin'] is False
    detail = _group_detail(client, group['id'], token_a)
    by_id = {p['user_id']: p for p in detail['participants']}
    assert by_id[str(user_b['id'])]['is_admin'] is False
    texts = _system_texts(client, group['id'], token_a)
    assert any(('demoted' in t for t in texts))
def test_non_admin_cannot_change_roles(api_client):
    client = api_client
    (token_a, user_a) = _register(client, EMAIL_A)
    (token_b, user_b) = _register(client, EMAIL_B)
    (token_c, user_c) = _register(client, EMAIL_C)
    _friend_each_with(client, token_a, [(token_b, user_b['id']), (token_c, user_c['id'])])
    _friend(client, token_b, user_c['id'], token_c)
    group = _create_group(client, token_a, 'Flat', [user_b['id'], user_c['id']])
    resp = client.post(f"/api/v1/conversations/{group['id']}/group/admin", json={'user_id': str(user_c['id']), 'is_admin': True}, headers=_auth(token_b))
    assert resp.status_code == 403
def test_cannot_demote_creator_or_last_admin(api_client):
    client = api_client
    (token_a, user_a) = _register(client, EMAIL_A)
    (token_b, user_b) = _register(client, EMAIL_B)
    _friend(client, token_a, user_b['id'], token_b)
    group = _create_group(client, token_a, 'LastAdmin', [user_b['id']])
    client.post(f"/api/v1/conversations/{group['id']}/group/admin", json={'user_id': str(user_b['id']), 'is_admin': True}, headers=_auth(token_a))
    resp = client.post(f"/api/v1/conversations/{group['id']}/group/admin", json={'user_id': str(user_a['id']), 'is_admin': False}, headers=_auth(token_b))
    assert resp.status_code == 400
    resp = client.post(f"/api/v1/conversations/{group['id']}/group/admin", json={'user_id': str(user_b['id']), 'is_admin': False}, headers=_auth(token_b))
    assert resp.status_code == 400, 'self-demotion is blocked'
def test_system_messages_track_group_lifecycle(api_client):
    client = api_client
    (token_a, user_a) = _register(client, EMAIL_A)
    (token_b, user_b) = _register(client, EMAIL_B)
    (token_c, user_c) = _register(client, EMAIL_C)
    _friend_each_with(client, token_a, [(token_b, user_b['id']), (token_c, user_c['id'])])
    _friend(client, token_b, user_c['id'], token_c)
    group = _create_group(client, token_a, 'Life', [user_b['id']])
    texts = _system_texts(client, group['id'], token_a)
    assert any(('created the group' in t for t in texts))
    client.post(f"/api/v1/conversations/{group['id']}/group/add", json={'member_ids': [str(user_c['id'])]}, headers=_auth(token_a))
    texts = _system_texts(client, group['id'], token_a)
    assert any(('added' in t for t in texts))
    client.post(f"/api/v1/conversations/{group['id']}/group/leave", headers=_auth(token_c))
    texts = _system_texts(client, group['id'], token_a)
    assert any(('left the group' in t for t in texts))
    assert _system_texts(client, group['id'], token_b)
def test_admin_uploads_group_avatar(api_client):
    client = api_client
    (token_a, user_a) = _register(client, EMAIL_A)
    (token_b, user_b) = _register(client, EMAIL_B)
    _friend(client, token_a, user_b['id'], token_b)
    group = _create_group(client, token_a, 'Avatars', [user_b['id']])
    png = b'\x89PNG\r\n\x1a\n' + b'0' * 64
    resp = client.post(f"/api/v1/conversations/{group['id']}/avatar", files={'file': ('group.png', io.BytesIO(png), 'image/png')}, headers=_auth(token_a))
    assert resp.status_code == 200, resp.text
    assert resp.json()['avatar_url'].endswith(f"/api/v1/conversations/{group['id']}/avatar")
    resp = client.get(f"/api/v1/conversations/{group['id']}/avatar", headers=_auth(token_b))
    assert resp.status_code == 200
    detail = _group_detail(client, group['id'], token_b)
    assert detail['avatar_url'].endswith(f"/api/v1/conversations/{group['id']}/avatar")
    texts = _system_texts(client, group['id'], token_a)
    assert any(('changed the group photo' in t for t in texts))
def test_group_avatar_rejects_disguised_script(api_client):
    client = api_client
    (token_a, user_a) = _register(client, EMAIL_A)
    (token_b, user_b) = _register(client, EMAIL_B)
    _friend(client, token_a, user_b['id'], token_b)
    group = _create_group(client, token_a, 'AvatarSniff', [user_b['id']])
    resp = client.post(f"/api/v1/conversations/{group['id']}/avatar", files={'file': ('group.png', io.BytesIO(b'<script>alert(1)</script>'), 'image/png')}, headers=_auth(token_a))
    assert resp.status_code == 400, resp.text
    assert 'does not match' in resp.json()['detail']
def test_non_admin_cannot_upload_avatar(api_client):
    client = api_client
    (token_a, user_a) = _register(client, EMAIL_A)
    (token_b, user_b) = _register(client, EMAIL_B)
    _friend(client, token_a, user_b['id'], token_b)
    group = _create_group(client, token_a, 'NoPhoto', [user_b['id']])
    png = b'\x89PNG\r\n\x1a\n' + b'0' * 64
    resp = client.post(f"/api/v1/conversations/{group['id']}/avatar", files={'file': ('group.png', io.BytesIO(png), 'image/png')}, headers=_auth(token_b))
    assert resp.status_code == 403
def test_avatar_missing_for_non_participant(api_client):
    client = api_client
    (token_a, user_a) = _register(client, EMAIL_A)
    (token_b, user_b) = _register(client, EMAIL_B)
    (token_c, user_c) = _register(client, EMAIL_C)
    _friend_each_with(client, token_a, [(token_b, user_b['id']), (token_c, user_c['id'])])
    group = _create_group(client, token_a, 'Secret', [user_b['id']])
    resp = client.get(f"/api/v1/conversations/{group['id']}/avatar", headers=_auth(token_c))
    assert resp.status_code == 404

# ======================================================================
# source: tests/test_message_features.py
# ======================================================================
'API tests for edit, emoji reactions and the forwarded flag.'
EMAIL_C__mfeat = 'mallory@example.com'
def _friend_and_conversation__mfeat(client, token_a, bob_id, token_b):
    resp = client.post('/api/v1/friends/request', json={'receiver_id': str(bob_id)}, headers=_auth(token_a))
    assert resp.status_code == 200, resp.text
    pending = client.get('/api/v1/friends/pending', headers=_auth(token_b)).json()
    friendship_id = pending[0]['id']
    resp = client.post('/api/v1/friends/accept', json={'friendship_id': str(friendship_id)}, headers=_auth(token_b))
    assert resp.status_code == 200, resp.text
    resp = client.post('/api/v1/conversations/private', json={'user_id': str(bob_id)}, headers=_auth(token_a))
    assert resp.status_code == 200, resp.text
    return resp.json()['id']
def _send__mfeat(client, conversation_id, token, content='payload'):
    resp = client.post('/api/v1/messages/send', json={'conversation_id': str(conversation_id), 'ciphertext': content, 'encrypted_key_sender': 'k1', 'encrypted_key_receiver': 'k2', 'nonce': 'n'}, headers=_auth(token))
    assert resp.status_code == 200, resp.text
    return resp.json()
def test_edit_message_replaces_ciphertext(api_client):
    client = api_client
    (token_a, _) = _register(client, EMAIL_A)
    (token_b, user_b) = _register(client, EMAIL_B)
    conversation_id = _friend_and_conversation__mfeat(client, token_a, user_b['id'], token_b)
    message = _send__mfeat(client, conversation_id, token_a, 'original-cipher')
    resp = client.put(f"/api/v1/messages/{message['id']}/edit", json={'ciphertext': 'edited-cipher', 'encrypted_key_sender': 'k1-new', 'encrypted_key_receiver': 'k2-new', 'nonce': 'n-new'}, headers=_auth(token_a))
    assert resp.status_code == 200, resp.text
    edited = resp.json()
    assert edited['edited'] is True
    assert edited['ciphertext'] == 'edited-cipher'
    assert edited['nonce'] == 'n-new'
    history = client.get(f'/api/v1/messages/{conversation_id}', headers=_auth(token_b)).json()
    assert history[0]['edited'] is True
    assert history[0]['ciphertext'] == 'edited-cipher'
def test_only_sender_can_edit(api_client):
    client = api_client
    (token_a, _) = _register(client, EMAIL_A)
    (token_b, user_b) = _register(client, EMAIL_B)
    conversation_id = _friend_and_conversation__mfeat(client, token_a, user_b['id'], token_b)
    message = _send__mfeat(client, conversation_id, token_a)
    resp = client.put(f"/api/v1/messages/{message['id']}/edit", json={'ciphertext': 'hacked-cipher', 'encrypted_key_sender': 'x', 'encrypted_key_receiver': 'y', 'nonce': 'z'}, headers=_auth(token_b))
    assert resp.status_code == 400
def test_cannot_edit_deleted_message(api_client):
    client = api_client
    (token_a, _) = _register(client, EMAIL_A)
    (token_b, user_b) = _register(client, EMAIL_B)
    conversation_id = _friend_and_conversation__mfeat(client, token_a, user_b['id'], token_b)
    message = _send__mfeat(client, conversation_id, token_a)
    resp = client.delete(f"/api/v1/messages/{message['id']}", headers=_auth(token_a))
    assert resp.status_code == 204
    resp = client.put(f"/api/v1/messages/{message['id']}/edit", json={'ciphertext': 'after-delete', 'encrypted_key_sender': 'x', 'encrypted_key_receiver': 'y', 'nonce': 'z'}, headers=_auth(token_a))
    assert resp.status_code == 400
def test_forwarded_flag_serialized(api_client):
    client = api_client
    (token_a, _) = _register(client, EMAIL_A)
    (token_b, user_b) = _register(client, EMAIL_B)
    conversation_id = _friend_and_conversation__mfeat(client, token_a, user_b['id'], token_b)
    resp = client.post('/api/v1/messages/send', json={'conversation_id': str(conversation_id), 'ciphertext': 'forwarded-cipher', 'encrypted_key_sender': 'k1', 'encrypted_key_receiver': 'k2', 'nonce': 'n', 'is_forwarded': True}, headers=_auth(token_a))
    assert resp.status_code == 200, resp.text
    assert resp.json()['is_forwarded'] is True
    history = client.get(f'/api/v1/messages/{conversation_id}', headers=_auth(token_b)).json()
    assert history[0]['is_forwarded'] is True
def test_reaction_add_and_list(api_client):
    client = api_client
    (token_a, _) = _register(client, EMAIL_A)
    (token_b, user_b) = _register(client, EMAIL_B)
    conversation_id = _friend_and_conversation__mfeat(client, token_a, user_b['id'], token_b)
    message = _send__mfeat(client, conversation_id, token_a)
    resp = client.put(f"/api/v1/messages/{message['id']}/reaction", json={'emoji': '👍'}, headers=_auth(token_b))
    assert resp.status_code == 200, resp.text
    assert resp.json()['action'] == 'add'
    assert resp.json()['emoji'] == '👍'
    history = client.get(f'/api/v1/messages/{conversation_id}', headers=_auth(token_a)).json()
    assert len(history[0]['reactions']) == 1
    assert history[0]['reactions'][0]['user_id'] == str(user_b['id'])
    assert history[0]['reactions'][0]['emoji'] == '👍'
def test_reaction_toggle_removes(api_client):
    client = api_client
    (token_a, _) = _register(client, EMAIL_A)
    (token_b, user_b) = _register(client, EMAIL_B)
    conversation_id = _friend_and_conversation__mfeat(client, token_a, user_b['id'], token_b)
    message = _send__mfeat(client, conversation_id, token_a)
    client.put(f"/api/v1/messages/{message['id']}/reaction", json={'emoji': '❤️'}, headers=_auth(token_b))
    resp = client.put(f"/api/v1/messages/{message['id']}/reaction", json={'emoji': '❤️'}, headers=_auth(token_b))
    assert resp.status_code == 200
    assert resp.json()['action'] == 'remove'
    history = client.get(f'/api/v1/messages/{conversation_id}', headers=_auth(token_a)).json()
    assert history[0]['reactions'] == []
def test_reaction_replaces_previous(api_client):
    client = api_client
    (token_a, _) = _register(client, EMAIL_A)
    (token_b, user_b) = _register(client, EMAIL_B)
    conversation_id = _friend_and_conversation__mfeat(client, token_a, user_b['id'], token_b)
    message = _send__mfeat(client, conversation_id, token_a)
    client.put(f"/api/v1/messages/{message['id']}/reaction", json={'emoji': '👍'}, headers=_auth(token_b))
    resp = client.put(f"/api/v1/messages/{message['id']}/reaction", json={'emoji': '😂'}, headers=_auth(token_b))
    assert resp.json()['action'] == 'add'
    history = client.get(f'/api/v1/messages/{conversation_id}', headers=_auth(token_a)).json()
    assert len(history[0]['reactions']) == 1
    assert history[0]['reactions'][0]['emoji'] == '😂'
def test_reaction_requires_participant(api_client):
    client = api_client
    (token_a, _) = _register(client, EMAIL_A)
    (token_b, user_b) = _register(client, EMAIL_B)
    (token_c, _) = _register(client, EMAIL_C__mfeat)
    conversation_id = _friend_and_conversation__mfeat(client, token_a, user_b['id'], token_b)
    message = _send__mfeat(client, conversation_id, token_a)
    resp = client.put(f"/api/v1/messages/{message['id']}/reaction", json={'emoji': '👍'}, headers=_auth(token_c))
    assert resp.status_code == 400

# ======================================================================
# source: tests/test_production_phase1.py
# ======================================================================
'Phase 1 production-readiness fixes:\n\n- attachment upload authorization (403 for non-participants)\n- attachment delete ownership (403 for non-sender, non-admin)\n- device re-registration ownership (403 cross-account)\n- user search requires auth (401)\n- push endpoint SSRF guard (400 for http / private IPs)\n- refresh-token reuse revokes the family (incl. pruned rows)\n- rate-limit client-IP resolution (XFF only honored when valid IP)\n'
EMAIL_C__p1 = 'mallory@example.com'
@pytest.fixture
def api_env(monkeypatch):
    """TestClient against an in-memory DB; returns (client, session_factory)."""
    monkeypatch.setattr(email_module.EmailService, 'send_otp_email', EmailRecorder.send_otp_email)
    EmailRecorder.sent = []
    reset_limiter()
    engine = create_async_engine('sqlite+aiosqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    TestingSessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr(conn_mgr, 'AsyncSessionLocal', TestingSessionLocal)

    async def override_get_db():
        async with TestingSessionLocal() as session:
            yield session

    async def setup():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    asyncio.run(setup())
    app_instance.dependency_overrides[get_db] = override_get_db
    with TestClient(app_instance) as client:
        yield (client, TestingSessionLocal)
    app_instance.dependency_overrides.clear()
def _register__p1(client, email):
    client.post('/api/v1/auth/send-otp', json={'email': email})
    otp = EmailRecorder.sent[-1]['otp']
    resp = client.post('/api/v1/auth/verify-otp', json={'email': email, 'otp': otp})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    return (data['access_token'], data['user'], data['refresh_token'])
def _friend_and_conversation__p1(client, token_a, bob_id, token_b):
    resp = client.post('/api/v1/friends/request', json={'receiver_id': str(bob_id)}, headers=_auth(token_a))
    assert resp.status_code == 200, resp.text
    pending = client.get('/api/v1/friends/pending', headers=_auth(token_b)).json()
    friendship_id = pending[0]['id']
    resp = client.post('/api/v1/friends/accept', json={'friendship_id': str(friendship_id)}, headers=_auth(token_b))
    assert resp.status_code == 200, resp.text
    resp = client.post('/api/v1/conversations/private', json={'user_id': str(bob_id)}, headers=_auth(token_a))
    assert resp.status_code == 200, resp.text
    return resp.json()['id']
def _upload_attachment(client, message_id, token):
    return client.post(f'/api/v1/attachments/upload/{message_id}', headers=_auth(token), files={'file': ('photo.jpg.bin', b'\x00' * 1024, 'application/octet-stream')})
def _device_key_material(opk_count: int=2, opk_start: int=1) -> dict:
    """Simulate client-side Signal key material (mirrors the
    payload the real client uploads)."""
    (identity_priv, identity_pub) = generate_ed25519_keypair()
    identity_x25519 = derive_x25519_from_ed25519(identity_priv)
    identity_x25519_pub = identity_x25519.public_key()
    (spk_priv, spk_pub) = generate_x25519_keypair()
    spk_pub_bytes = x25519_public_to_bytes(spk_pub)
    signature = ed25519_sign(identity_priv, spk_pub_bytes)
    opks = []
    for kid in range(opk_start, opk_start + opk_count):
        (p, q) = generate_x25519_keypair()
        opks.append({'key_id': kid, 'public_key': b64encode(x25519_public_to_bytes(q))})
    return {'identity_key_public': b64encode(ed25519_public_to_bytes(identity_pub)), 'identity_key_x25519': b64encode(x25519_public_to_bytes(identity_x25519_pub)), 'signed_prekey_public': b64encode(spk_pub_bytes), 'signed_prekey_id': 1, 'signed_prekey_signature': b64encode(signature), 'one_time_prekeys': opks}
def _register_device(client, token, device_id, opk_start: int=1):
    return client.post('/api/v1/devices/register', json={'device_id': device_id, 'platform': 'web', 'device_name': 'Test', **_device_key_material(opk_start=opk_start)}, headers=_auth(token))
def test_attachment_upload_rejected_for_non_participant(api_env):
    (client, _) = api_env
    (token_a, user_a, _) = _register__p1(client, EMAIL_A)
    (token_b, user_b, _) = _register__p1(client, EMAIL_B)
    (token_c, _, _) = _register__p1(client, EMAIL_C__p1)
    conversation_id = _friend_and_conversation__p1(client, token_a, user_b['id'], token_b)
    message = _send_message(client, conversation_id, token_a)
    resp = _upload_attachment(client, message['id'], token_c)
    assert resp.status_code == 403, resp.text
    resp = _upload_attachment(client, message['id'], token_a)
    assert resp.status_code == 200, resp.text
def test_attachment_delete_requires_sender(api_env):
    (client, _) = api_env
    (token_a, user_a, _) = _register__p1(client, EMAIL_A)
    (token_b, user_b, _) = _register__p1(client, EMAIL_B)
    conversation_id = _friend_and_conversation__p1(client, token_a, user_b['id'], token_b)
    message = _send_message(client, conversation_id, token_a)
    attachment = _upload_attachment(client, message['id'], token_a).json()['attachment']
    attachment_id = attachment['id']
    resp = client.delete(f'/api/v1/attachments/{attachment_id}', headers=_auth(token_b))
    assert resp.status_code == 403, resp.text
    resp = client.delete(f'/api/v1/attachments/{attachment_id}', headers=_auth(token_a))
    assert resp.status_code == 200, resp.text
def test_device_re_registration_blocked_across_accounts(api_env):
    (client, _) = api_env
    (token_a, _, _) = _register__p1(client, EMAIL_A)
    (token_b, _, _) = _register__p1(client, EMAIL_B)
    device_id = 'web-hijack-target'
    resp = _register_device(client, token_a, device_id)
    assert resp.status_code == 200, resp.text
    resp = _register_device(client, token_b, device_id)
    assert resp.status_code == 403, resp.text
    resp = _register_device(client, token_a, device_id, opk_start=10)
    assert resp.status_code == 200, resp.text
def test_user_search_requires_auth(api_env):
    (client, _) = api_env
    (token_a, _, _) = _register__p1(client, EMAIL_A)
    resp = client.get('/api/v1/users/search', params={'q': 'alice@example.com'})
    assert resp.status_code == 401, resp.text
    resp = client.get('/api/v1/users/search', params={'q': 'alice@example.com'}, headers=_auth(token_a))
    assert resp.status_code == 200, resp.text
def _subscribe_push(client, token, endpoint):
    return client.post('/api/v1/push/subscribe', json={'endpoint': endpoint, 'p256dh': 'dummy', 'auth': 'dummy'}, headers=_auth(token))
def test_push_endpoint_rejects_http_and_private_ips(api_env):
    (client, _) = api_env
    (token_a, _, _) = _register__p1(client, EMAIL_A)
    for bad_endpoint in ['http://fcm.googleapis.com/push/abc', 'https://192.168.1.5/push', 'https://169.254.169.254/latest/meta-data', 'https://10.0.0.1/push', 'https://localhost/push', 'https://[::1]/push', 'https://backend/push', 'https://redis/push']:
        resp = _subscribe_push(client, token_a, bad_endpoint)
        assert resp.status_code == 400, f'expected 400 for {bad_endpoint}, got {resp.status_code}: ' + resp.text
def test_push_endpoint_accepts_public_https(api_env):
    (client, _) = api_env
    (token_a, _, _) = _register__p1(client, EMAIL_A)
    resp = _subscribe_push(client, token_a, 'https://fcm.googleapis.com/fcm/send/abc123')
    assert resp.status_code == 200, resp.text
def test_refresh_reuse_revokes_family(api_env):
    (client, _) = api_env
    (_, _, refresh_1) = _register__p1(client, EMAIL_A)
    resp = client.post('/api/v1/auth/refresh', json={'refresh_token': refresh_1})
    assert resp.status_code == 200, resp.text
    refresh_2 = resp.json()['refresh_token']
    client.cookies.clear()
    resp = client.post('/api/v1/auth/refresh', json={'refresh_token': refresh_1})
    assert resp.status_code == 401, resp.text
    resp = client.post('/api/v1/auth/refresh', json={'refresh_token': refresh_2})
    assert resp.status_code == 401, resp.text
def test_refresh_reuse_revokes_family_after_row_prune(api_env):
    """The `record is None` path: after the rotated-away row is
    pruned (token cleanup), a replayed token must still be traced
    back to its family via its jti and revoke it."""
    (client, TestingSessionLocal) = api_env
    (_, _, refresh_1) = _register__p1(client, EMAIL_A)
    resp = client.post('/api/v1/auth/refresh', json={'refresh_token': refresh_1})
    assert resp.status_code == 200, resp.text
    refresh_2 = resp.json()['refresh_token']

    async def prune():
        async with TestingSessionLocal() as session:
            await session.execute(delete(RefreshToken).where(RefreshToken.token_hash == RefreshTokenRepository.hash_token(refresh_1)))
            await session.commit()
    asyncio.run(prune())
    client.cookies.clear()
    resp = client.post('/api/v1/auth/refresh', json={'refresh_token': refresh_1})
    assert resp.status_code == 401, resp.text
    resp = client.post('/api/v1/auth/refresh', json={'refresh_token': refresh_2})
    assert resp.status_code == 401, resp.text
class _FakeClient:

    def __init__(self, host):
        self.host = host
class _FakeRequest:

    def __init__(self, headers, client_host):
        self.headers = headers
        self.client = _FakeClient(client_host)
def test_client_ip_only_honors_valid_xff():
    assert limiter_client_ip(_FakeRequest({'x-forwarded-for': '203.0.113.9'}, '10.0.0.2')) == '203.0.113.9'
    assert limiter_client_ip(_FakeRequest({'x-forwarded-for': 'garbage'}, '10.0.0.2')) == '10.0.0.2'
    assert limiter_client_ip(_FakeRequest({}, '10.0.0.2')) == '10.0.0.2'

# ======================================================================
# source: tests/test_push.py
# ======================================================================
"API + service tests for Web Push (VAPID) notifications.\n\nSubscriptions are stored per user; the VAPID keypair is\ngenerated once and persisted. Deliveries are end-to-end\nencrypted with the subscription's p256dh/auth keys (aes128gcm),\nso the payload is verifiably unreadable by the push provider.\n"
@pytest.fixture
def api_client__push(monkeypatch):
    monkeypatch.setattr(email_module.EmailService, 'send_otp_email', EmailRecorder.send_otp_email)
    EmailRecorder.sent = []
    reset_limiter()
    engine = create_async_engine('sqlite+aiosqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    TestingSessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr(conn_mgr, 'AsyncSessionLocal', TestingSessionLocal)
    monkeypatch.setattr(db_session_module, 'AsyncSessionLocal', TestingSessionLocal)
    import app.services.push_service as push_module
    monkeypatch.setattr(push_module, 'AsyncSessionLocal', TestingSessionLocal)

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
def _make_subscription():
    """Generate a (fake) browser push subscription keypair."""
    private_key = ec.generate_private_key(ec.SECP256R1())
    public_bytes = private_key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    p256dh = base64.urlsafe_b64encode(public_bytes).rstrip(b'=').decode()
    auth = base64.urlsafe_b64encode(b'0123456789abcdef').rstrip(b'=').decode()
    return (private_key, p256dh, auth)
def test_subscribe_list_unsubscribe(api_client__push):
    client = api_client__push
    (token, user) = _register(client, EMAIL_A)
    (_, p256dh, auth) = _make_subscription()
    resp = client.post('/api/v1/push/subscribe', json={'endpoint': 'https://push.example.com/abc/xyz', 'p256dh': p256dh, 'auth': auth}, headers=_auth(token))
    assert resp.status_code == 200, resp.text
    subscription_id = resp.json()['id']
    resp = client.post('/api/v1/push/subscribe', json={'endpoint': 'https://push.example.com/abc/xyz', 'p256dh': p256dh, 'auth': auth}, headers=_auth(token))
    assert resp.status_code == 200
    assert resp.json()['status'] == 'existing'
    resp = client.get('/api/v1/push/subscriptions', headers=_auth(token))
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 1
    assert items[0]['id'] == subscription_id
    resp = client.delete(f'/api/v1/push/subscriptions/{subscription_id}', headers=_auth(token))
    assert resp.status_code == 200
    resp = client.get('/api/v1/push/subscriptions', headers=_auth(token))
    assert resp.status_code == 200
    assert resp.json() == []
def test_vapid_public_key_endpoint(api_client__push):
    client = api_client__push
    (token, user) = _register(client, EMAIL_A)
    resp = client.get('/api/v1/push/vapid-public-key', headers=_auth(token))
    assert resp.status_code == 200, resp.text
    public_key = resp.json()['public_key']
    assert len(public_key) >= 80
def test_subscribe_rejects_bad_endpoint(api_client__push):
    client = api_client__push
    (token, user) = _register(client, EMAIL_A)
    (_, p256dh, auth) = _make_subscription()
    resp = client.post('/api/v1/push/subscribe', json={'endpoint': 'not-a-url', 'p256dh': p256dh, 'auth': auth}, headers=_auth(token))
    assert resp.status_code == 400
def test_notify_user_delivers_encrypted_payload(api_client__push, monkeypatch):
    client = api_client__push
    (token, user) = _register(client, EMAIL_A)
    (private_key, p256dh, auth) = _make_subscription()
    client.post('/api/v1/push/subscribe', json={'endpoint': 'https://push.example.com/endpoint-1', 'p256dh': p256dh, 'auth': auth}, headers=_auth(token))
    sent = {}

    class FakeResponse:
        status_code = 201
        text = 'ok'

    async def fake_post(url, content=None, headers=None):
        sent['url'] = url
        sent['content'] = content
        sent['headers'] = headers
        return FakeResponse()
    import app.services.push_service as push_module
    from app.services.push_service import push_service

    def fake_client():
        return type('C', (), {'post': fake_post, 'is_closed': False})
    monkeypatch.setattr(push_module, '_http_client', fake_client)

    async def run():
        from uuid import UUID
        await push_service.notify_user(UUID(user['id']), {'event': 'test', 'hello': 'world'})
    asyncio.run(run())
    assert sent['url'] == 'https://push.example.com/endpoint-1'
    auth_header = sent['headers']['Authorization']
    assert auth_header.startswith('vapid t=')
    assert ', k=' in auth_header
    assert sent['headers']['Content-Encoding'] == 'aes128gcm'
    decrypted = ece_decrypt(sent['content'], private_key=private_key, auth_secret=base64.urlsafe_b64decode(auth + '=='))
    payload = json.loads(decrypted)
    assert payload['event'] == 'test'
    assert payload['hello'] == 'world'
def test_dead_subscription_is_dropped(api_client__push, monkeypatch):
    client = api_client__push
    (token, user) = _register(client, EMAIL_A)
    (_, p256dh, auth) = _make_subscription()
    client.post('/api/v1/push/subscribe', json={'endpoint': 'https://push.example.com/dead', 'p256dh': p256dh, 'auth': auth}, headers=_auth(token))

    class FakeResponse:
        status_code = 410
        text = 'gone'

    async def fake_post(url, content=None, headers=None):
        return FakeResponse()
    import app.services.push_service as push_module
    from app.services.push_service import push_service

    def fake_client():
        return type('C', (), {'post': fake_post, 'is_closed': False})
    monkeypatch.setattr(push_module, '_http_client', fake_client)

    async def run():
        from uuid import UUID
        await push_service.notify_user(UUID(user['id']), {'event': 'test'})
    asyncio.run(run())
    resp = client.get('/api/v1/push/subscriptions', headers=_auth(token))
    assert resp.json() == []

# ======================================================================
'Tests for the "I lost my recovery code" re-issue flow.'
class EmailRecorder__reci:
    sent: list[dict] = []

    @classmethod
    async def send_otp_email(cls, recipient_email: str, otp: str, **kwargs):
        cls.sent.append({'email': recipient_email, 'otp': otp})

    @classmethod
    async def send_recovery_link_email(cls, recipient_email: str, link_url: str, **kwargs):
        cls.sent.append({'email': recipient_email, 'link': link_url})
@pytest.fixture
def api_client__reci(monkeypatch):
    monkeypatch.setattr(email_module.EmailService, 'send_otp_email', EmailRecorder__reci.send_otp_email)
    monkeypatch.setattr(email_module.EmailService, 'send_recovery_link_email', EmailRecorder__reci.send_recovery_link_email)
    EmailRecorder__reci.sent = []
    recovery_token_store.clear()
    reset_limiter()
    engine = create_async_engine('sqlite+aiosqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    TestingSessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr(conn_mgr, 'AsyncSessionLocal', TestingSessionLocal)

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
def _register__reci(client, email):
    client.post('/api/v1/auth/send-otp', json={'email': email})
    otp = EmailRecorder__reci.sent[-1]['otp']
    resp = client.post('/api/v1/auth/verify-otp', json={'email': email, 'otp': otp})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    return (data['access_token'], data['user'])
def make_key_material__reci() -> dict:
    (identity_priv, identity_pub) = generate_ed25519_keypair()
    identity_x25519 = derive_x25519_from_ed25519(identity_priv)
    identity_x25519_pub = identity_x25519.public_key()
    (spk_priv, spk_pub) = generate_x25519_keypair()
    spk_pub_bytes = x25519_public_to_bytes(spk_pub)
    signature = ed25519_sign(identity_priv, spk_pub_bytes)
    opks = []
    for kid in range(1, 3):
        (p, q) = generate_x25519_keypair()
        opks.append({'key_id': kid, 'public_key': b64encode(x25519_public_to_bytes(q))})
    return {'identity_key_public': b64encode(ed25519_public_to_bytes(identity_pub)), 'identity_key_x25519': b64encode(x25519_public_to_bytes(identity_x25519_pub)), 'signed_prekey_public': b64encode(spk_pub_bytes), 'signed_prekey_id': 1, 'signed_prekey_signature': b64encode(signature), 'one_time_prekeys': opks}
def _register_device__reci(client, token, device_id):
    resp = client.post('/api/v1/devices/register', json={'device_id': device_id, 'platform': 'web', 'device_name': 'Test Browser', **make_key_material__reci()}, headers=_auth(token))
    assert resp.status_code == 200, resp.text
    return resp.json()
def _create_account_with_secret(client, email=EMAIL_A):
    """Register + register a device: account gets a recovery code."""
    (token, user) = _register(client, email)
    device = _register_device__reci(client, token, f'dev-{uuid.uuid4().hex[:8]}')
    assert device['recovery_code'], 'first registration mints a code'
    return (token, user, device)
def _link_from_emails():
    link = [e for e in EmailRecorder__reci.sent if e.get('link')][-1]['link']
    return link.split('token=')[1]
def _send_otp_for(client, email):
    client.post('/api/v1/auth/send-otp', json={'email': email})
    return EmailRecorder__reci.sent[-1]['otp']
def test_recovery_request_requires_auth(api_client__reci):
    resp = api_client__reci.post('/api/v1/recovery/request', json={})
    assert resp.status_code == 401
def test_recovery_request_rewraps_same_secret(api_client__reci):
    (token, _, device) = _create_account_with_secret(api_client__reci)
    secret = unlock_sync_secret(device['recovery_code'].replace('-', ''), device['recovery_salt'], device['recovery_wrapped_key'])
    assert secret, 'the original code unlocks the secret'
    resp = api_client__reci.post('/api/v1/recovery/request', json={'secret_b64': secret}, headers=_auth(token))
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data['mode'] == 'same_secret'
    assert data['remaining'] == 2
    assert data['retry_after'] <= 600
    assert 'link' in [e for e in EmailRecorder__reci.sent if e.get('link')][-1]
    current = api_client__reci.get('/api/v1/recovery/unlock', headers=_auth(token)).json()
    assert unlock_sync_secret(device['recovery_code'].replace('-', ''), current['salt'], current['wrapped_key']) is None
    otp = _send_otp_for(api_client__reci, EMAIL_A)
    token_val = _link_from_emails()
    resp = api_client__reci.post('/api/v1/recovery/verify', json={'token': token_val, 'email': EMAIL_A, 'otp': otp})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data['code_display'] != device['recovery_code']
    recovered = unlock_sync_secret(data['code'].replace('-', ''), data['salt'], data['wrapped_key'])
    assert recovered == secret, 'the SAME secret is re-wrapped'
def test_recovery_request_mints_fresh_key_without_secret(api_client__reci):
    (token, _, device) = _create_account_with_secret(api_client__reci)
    old_secret = unlock_sync_secret(device['recovery_code'].replace('-', ''), device['recovery_salt'], device['recovery_wrapped_key'])
    resp = api_client__reci.post('/api/v1/recovery/request', json={}, headers=_auth(token))
    assert resp.status_code == 200, resp.text
    assert resp.json()['mode'] == 'new_secret'
    otp = _send_otp_for(api_client__reci, EMAIL_A)
    resp = api_client__reci.post('/api/v1/recovery/verify', json={'token': _link_from_emails(), 'email': EMAIL_A, 'otp': otp})
    data = resp.json()
    new_secret = unlock_sync_secret(data['code'].replace('-', ''), data['salt'], data['wrapped_key'])
    assert new_secret is not None
    assert new_secret != old_secret, 'fresh mint -> brand-new secret'
def test_recovery_request_rejects_bad_secret(api_client__reci):
    (token, _, _) = _create_account_with_secret(api_client__reci)
    resp = api_client__reci.post('/api/v1/recovery/request', json={'secret_b64': 'bm90LWEtc2VjcmV0IQ=='}, headers=_auth(token))
    assert resp.status_code == 400
def test_recovery_request_rate_limited_per_email(api_client__reci):
    (token, _, _) = _create_account_with_secret(api_client__reci)
    for _ in range(3):
        resp = api_client__reci.post('/api/v1/recovery/request', json={}, headers=_auth(token))
        assert resp.status_code == 200, resp.text
    resp = api_client__reci.post('/api/v1/recovery/request', json={}, headers=_auth(token))
    assert resp.status_code == 429
    assert 'Retry-After' in resp.headers
def test_recovery_re_request_revokes_previous_link(api_client__reci):
    (token, _, _) = _create_account_with_secret(api_client__reci)
    api_client__reci.post('/api/v1/recovery/request', json={}, headers=_auth(token))
    first_token = _link_from_emails()
    api_client__reci.post('/api/v1/recovery/request', json={}, headers=_auth(token))
    otp = _send_otp_for(api_client__reci, EMAIL_A)
    resp = api_client__reci.post('/api/v1/recovery/verify', json={'token': first_token, 'email': EMAIL_A, 'otp': otp})
    assert resp.status_code == 404, 'superseded link is dead'
def test_recovery_verify_rejects_bad_token(api_client__reci):
    (token, _, _) = _create_account_with_secret(api_client__reci)
    api_client__reci.post('/api/v1/recovery/request', json={}, headers=_auth(token))
    resp = api_client__reci.post('/api/v1/recovery/verify', json={'token': 'garbage-token', 'email': EMAIL_A, 'otp': '123456'})
    assert resp.status_code == 404
def test_recovery_verify_rejects_wrong_email(api_client__reci):
    (token, _, _) = _create_account_with_secret(api_client__reci)
    api_client__reci.post('/api/v1/recovery/request', json={}, headers=_auth(token))
    otp = _send_otp_for(api_client__reci, EMAIL_A)
    resp = api_client__reci.post('/api/v1/recovery/verify', json={'token': _link_from_emails(), 'email': 'mallory@example.com', 'otp': otp})
    assert resp.status_code == 403
def test_recovery_verify_rejects_wrong_otp(api_client__reci):
    (token, _, _) = _create_account_with_secret(api_client__reci)
    api_client__reci.post('/api/v1/recovery/request', json={}, headers=_auth(token))
    resp = api_client__reci.post('/api/v1/recovery/verify', json={'token': _link_from_emails(), 'email': EMAIL_A, 'otp': '000000'})
    assert resp.status_code == 400
def test_recovery_verify_consumes_otp_once(api_client__reci):
    (token, _, _) = _create_account_with_secret(api_client__reci)
    api_client__reci.post('/api/v1/recovery/request', json={}, headers=_auth(token))
    otp = _send_otp_for(api_client__reci, EMAIL_A)
    resp = api_client__reci.post('/api/v1/recovery/verify', json={'token': _link_from_emails(), 'email': EMAIL_A, 'otp': otp})
    assert resp.status_code == 200, resp.text
    resp = api_client__reci.post('/api/v1/recovery/verify', json={'token': _link_from_emails(), 'email': EMAIL_A, 'otp': otp})
    assert resp.status_code == 404, 'token consumed on success'
