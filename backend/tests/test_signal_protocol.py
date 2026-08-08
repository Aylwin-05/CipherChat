"""
Signal Protocol unit tests: primitives, X3DH, double ratchet, envelope.
Run: pytest tests/test_signal_protocol.py -v
"""

import pytest

from app.crypto.signal.primitives import (
    generate_x25519_keypair,
    generate_ed25519_keypair,
    x25519_dh,
    x25519_public_to_bytes,
    ed25519_public_to_bytes,
    ed25519_sign,
    ed25519_verify,
    kdf_root_chain,
    kdf_chain_key,
    aes_gcm_encrypt,
    aes_gcm_decrypt,
    generate_symmetric_key,
    generate_nonce,
)
from app.crypto.signal.double_ratchet import (
    kdf_root_chain_step,
    kdf_chain_key_step,
    derive_message_keys,
    DoubleRatchetCore,
    RatchetState,
    DHKeyPair,
    Chain,
)
from app.crypto.signal.message import (
    SignalEnvelope,
    EnvelopeError,
    build_prekey_message,
    parse_prekey_message,
)


# ==========================================================
# Primitives
# ==========================================================

class TestPrimitives:
    def test_x25519_dh_matches(self):
        pa, _ = generate_x25519_keypair()
        pb, _ = generate_x25519_keypair()
        # derive public peers to build DH tuples
        a, A = generate_x25519_keypair()
        b, B = generate_x25519_keypair()
        assert x25519_dh(a, B) == x25519_dh(b, A)

    def test_ed25519_sign_verify(self):
        p, pub = generate_ed25519_keypair()
        sig = ed25519_sign(p, b"hello")
        assert ed25519_verify(pub, sig, b"hello") is True
        assert ed25519_verify(pub, sig, b"tampered") is False

    def test_kdf_root_chain(self):
        root = b"R" * 32
        dh = b"D" * 32
        new_root, chain = kdf_root_chain(root, dh)
        assert len(new_root) == 32
        assert len(chain) == 32

    def test_kdf_chain_key(self):
        ck = b"C" * 32
        next_ck, mk = kdf_chain_key(ck)
        assert len(next_ck) == 32 and len(mk) == 32
        assert next_ck != mk

    def test_aes_gcm_roundtrip(self):
        key = generate_symmetric_key()
        nonce = generate_nonce()
        ad = b"AD"
        ct, used_nonce = aes_gcm_encrypt(key, b"secret", ad, nonce)
        assert aes_gcm_decrypt(key, ct, ad, used_nonce) == b"secret"

    def test_aes_gcm_tamper_fails(self):
        key = generate_symmetric_key()
        nonce = generate_nonce()
        ct, used = aes_gcm_encrypt(key, b"secret", b"AD", nonce)
        tampered = ct[:-1] + bytes([ct[-1] ^ 1])
        with pytest.raises(Exception):
            aes_gcm_decrypt(key, tampered, b"AD", used)


# ==========================================================
# Double Ratchet (KDF steps + state)
# ==========================================================

class TestDoubleRatchetCore:
    def test_kdf_steps_lengths(self):
        new_root, ck = kdf_root_chain_step(b"R" * 32, b"D" * 32)
        assert len(new_root) == 32 and len(ck) == 32
        next_ck, mk = kdf_chain_key_step(ck)
        assert len(next_ck) == 32 and len(mk) == 32

    def test_message_key_derivation_deterministic(self):
        e1, a1, n1 = derive_message_keys(b"MK" * 16)
        e2, a2, n2 = derive_message_keys(b"MK" * 16)
        assert e1 == e2 and a1 == a2 and n1 == n2
        assert len(e1) == 32 and len(a1) == 32

    def test_state_roundtrip(self):
        state = RatchetState(
            root_key=b"R" * 32,
            our_dh_pair=DHKeyPair.new(),
            their_dh_public=b"T" * 32,
            sending_chain=Chain(key=b"S" * 32, index=5),
            receiving_chain=Chain(key=b"C" * 32, index=3),
            skipped_message_keys={},
            associated_data=b"AD" * 8,
        )
        state2 = RatchetState.from_dict(state.to_dict())
        assert state2.root_key == state.root_key
        assert state2.our_dh_pair.public_raw == state.our_dh_pair.public_raw
        assert state2.sending_chain.index == 5

    def test_bidirectional_ratchet(self):
        shared = b"S" * 32
        ad = b"AD" * 8
        alice = DoubleRatchetCore(shared, ad)
        bob = DoubleRatchetCore(shared, ad)

        # Alice is initiator
        alice.their_dh_public = bob.our_dh_pair.public_raw
        alice.initialize_initiator()

        h1, p1 = alice.encrypt_message(b"Hello")
        assert bob.decrypt_message(h1, p1) == b"Hello"

        h2, p2 = bob.encrypt_message(b"Hi")
        assert alice.decrypt_message(h2, p2) == b"Hi"

        # 20 messages each way
        for i in range(20):
            h, p = alice.encrypt_message(f"A{i}".encode())
            assert bob.decrypt_message(h, p) == f"A{i}".encode()
            h, p = bob.encrypt_message(f"B{i}".encode())
            assert alice.decrypt_message(h, p) == f"B{i}".encode()

    def test_out_of_order(self):
        shared = b"S" * 32
        ad = b"AD" * 8
        alice = DoubleRatchetCore(shared, ad)
        bob = DoubleRatchetCore(shared, ad)
        alice.their_dh_public = bob.our_dh_pair.public_raw
        alice.initialize_initiator()

        msgs = []
        for i in range(5):
            h, p = alice.encrypt_message(f"M{i}".encode())
            msgs.append((h, p))

        for i in [2, 0, 1, 4, 3]:
            assert bob.decrypt_message(*msgs[i]) == f"M{i}".encode()

        # replay rejected
        with pytest.raises(ValueError):
            bob.decrypt_message(*msgs[0])

    def test_state_save_restore(self):
        ad = b"AD" * 8
        alice = DoubleRatchetCore(b"S" * 32, ad)
        bob = DoubleRatchetCore(b"S" * 32, ad)
        alice.their_dh_public = bob.our_dh_pair.public_raw
        alice.initialize_initiator()

        for i in range(3):
            h, p = alice.encrypt_message(f"M{i}".encode())
            bob.decrypt_message(h, p)

        restored = DoubleRatchetCore.from_state(
            RatchetState.from_dict(alice.state().to_dict())
        )
        h, p = restored.encrypt_message(b"M3")
        assert bob.decrypt_message(h, p) == b"M3"


# ==========================================================
# Envelope
# ==========================================================

class TestEnvelope:
    def test_prekey_roundtrip(self):
        ik, _ = generate_ed25519_keypair()
        ek, _ = generate_x25519_keypair()
        env = build_prekey_message(
            device_id="d1",
            sender_id="u1",
            our_identity_private=ik,
            our_ephemeral_private=ek,
            ratchet_header={"pn": 0, "n": 0, "dh": "ab" * 32},
            ciphertext=b"\x01\x02",
            signed_prekey_id=1,
            one_time_prekey_id=3,
        )
        env2 = SignalEnvelope.from_json(env.to_json())
        info = parse_prekey_message(env2)
        assert info["signed_prekey_id"] == 1
        assert info["one_time_prekey_id"] == 3

    def test_malformed_rejected(self):
        with pytest.raises(EnvelopeError):
            SignalEnvelope.from_json("not json")
        with pytest.raises(EnvelopeError):
            SignalEnvelope.from_json(
                '{"type":"data","version":99,"device_id":"d","sender_id":"s",'
                '"ratchet":{},"ciphertext":""}'
            )