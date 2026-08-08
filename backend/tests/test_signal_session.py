"""
Session manager integration tests (X3DH handshake + double ratchet).
Run: pytest tests/test_signal_session.py -v
"""

import asyncio

import pytest

from app.crypto.signal.session import (
    SignalSessionManager,
    InMemorySessionStore,
)
from app.crypto.signal.primitives import (
    generate_ed25519_keypair,
    generate_x25519_keypair,
    ed25519_private_to_bytes,
    x25519_private_to_bytes,
    b64encode,
)
from app.crypto.signal.x3dh import create_key_bundle
from app.crypto.signal.double_ratchet import RatchetState


@pytest.mark.asyncio
async def test_full_session_flow():
    # --- Bob's device + bundle ---
    bob_ik, _ = generate_ed25519_keypair()
    bob_spk, _ = generate_x25519_keypair()
    bob_opk, _ = generate_x25519_keypair()
    bundle = create_key_bundle(
        device_id="bob-device-1",
        identity_private=bob_ik,
        signed_prekey_private=bob_spk,
        signed_prekey_id=1,
        one_time_prekeys=[(7, bob_opk)],
    ).to_dict()

    alice_ik, _ = generate_ed25519_keypair()

    alice = SignalSessionManager(InMemorySessionStore())
    bob = SignalSessionManager(InMemorySessionStore())

    # --- Alice first message (X3DH) ---
    env1 = await alice.encrypt_first(
        our_device_id="alice-device-1",
        our_user_id="user-alice",
        our_identity_private=ed25519_private_to_bytes(alice_ik),
        their_device_id="bob-device-1",
        their_bundle=bundle,
        conversation_id="conv-1",
        plaintext=b"Hello Bob, this is Alice!",
    )
    assert env1.type == "prekey"

    res1 = await bob.decrypt_first(
        envelope=env1,
        our_device_id="bob-device-1",
        our_user_id="user-bob",
        our_identity_private=ed25519_private_to_bytes(bob_ik),
        signed_prekey={
            "key_id": 1,
            "private_key": b64encode(x25519_private_to_bytes(bob_spk)),
        },
        one_time_prekey={
            "key_id": 7,
            "private_key": b64encode(x25519_private_to_bytes(bob_opk)),
        },
        conversation_id="conv-1",
    )
    assert res1.plaintext == b"Hello Bob, this is Alice!"
    assert res1.new_session is True

    # --- Bob replies ---
    env2 = await bob.encrypt(
        our_device_id="bob-device-1",
        our_user_id="user-bob",
        remote_device_id="alice-device-1",
        conversation_id="conv-1",
        plaintext=b"Hello Alice, message received!",
    )
    res2 = await alice.decrypt(
        envelope=env2,
        our_device_id="alice-device-1",
        conversation_id="conv-1",
    )
    assert res2.plaintext == b"Hello Alice, message received!"

    # --- 10 more messages each way ---
    for i in range(10):
        env = await alice.encrypt(
            our_device_id="alice-device-1",
            our_user_id="user-alice",
            remote_device_id="bob-device-1",
            conversation_id="conv-1",
            plaintext=f"A{i}".encode(),
        )
        assert (await bob.decrypt(
            envelope=env, our_device_id="bob-device-1", conversation_id="conv-1"
        )).plaintext == f"A{i}".encode()

        env = await bob.encrypt(
            our_device_id="bob-device-1",
            our_user_id="user-bob",
            remote_device_id="alice-device-1",
            conversation_id="conv-1",
            plaintext=f"B{i}".encode(),
        )
        assert (await alice.decrypt(
            envelope=env, our_device_id="alice-device-1", conversation_id="conv-1"
        )).plaintext == f"B{i}".encode()


@pytest.mark.asyncio
async def test_session_state_persistence():
    bob_ik, _ = generate_ed25519_keypair()
    bob_spk, _ = generate_x25519_keypair()
    bob_opk, _ = generate_x25519_keypair()
    alice_ik, _ = generate_ed25519_keypair()
    bundle = create_key_bundle(
        device_id="bob-device-1",
        identity_private=bob_ik,
        signed_prekey_private=bob_spk,
        signed_prekey_id=1,
        one_time_prekeys=[(1, bob_opk)],
    ).to_dict()

    alice_store = InMemorySessionStore()
    bob_store = InMemorySessionStore()
    alice = SignalSessionManager(alice_store)
    bob = SignalSessionManager(bob_store)

    env1 = await alice.encrypt_first(
        our_device_id="a-1", our_user_id="u-a",
        our_identity_private=ed25519_private_to_bytes(alice_ik),
        their_device_id="b-1", their_bundle=bundle,
        conversation_id="c-1", plaintext=b"first",
    )
    await bob.decrypt_first(
        envelope=env1, our_device_id="b-1", our_user_id="u-b",
        our_identity_private=ed25519_private_to_bytes(bob_ik),
        signed_prekey={"key_id": 1,
                       "private_key": b64encode(x25519_private_to_bytes(bob_spk))},
        one_time_prekey={"key_id": 1,
                         "private_key": b64encode(x25519_private_to_bytes(bob_opk))},
        conversation_id="c-1",
    )

    # Simulate alice restarting: restore from serialized state
    saved = await alice_store.get("a-1", "b-1", "c-1")
    data = saved.to_dict()
    restored = RatchetState.from_dict(data)
    assert restored.root_key == saved.root_key

    # Messages still work after restore
    env = await alice.encrypt(
        our_device_id="a-1", our_user_id="u-a",
        remote_device_id="b-1", conversation_id="c-1",
        plaintext=b"after restart",
    )
    res = await bob.decrypt(
        envelope=env, our_device_id="b-1", conversation_id="c-1"
    )
    assert res.plaintext == b"after restart"


@pytest.mark.asyncio
async def test_no_session_raises():
    mgr = SignalSessionManager(InMemorySessionStore())
    with pytest.raises(Exception):
        await mgr.encrypt(
            our_device_id="a", our_user_id="u1",
            remote_device_id="b-1", conversation_id="c-1",
            plaintext=b"hi",
        )