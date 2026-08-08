"""
Double Ratchet State

This module implements the core state for the Double Ratchet algorithm
(Signal Protocol). Focused on one thing: managing the ratchet state
and performing key derivation steps.

Per https://signal.org/docs/specifications/doubleratchet/
"""

import json
from dataclasses import dataclass, field
from typing import Optional

from app.crypto.signal.primitives import (
    x25519_private_from_bytes,
    x25519_public_from_bytes,
    x25519_private_to_bytes,
    x25519_public_to_bytes,
    generate_x25519_keypair,
    x25519_dh,
    hkdf,
    aes_gcm_encrypt,
    aes_gcm_decrypt,
    HKDF_INFO_ROOT_CHAIN,
)

# ==========================================================
# KDF Functions (Signal spec section 3.3, 3.4)
# ==========================================================

def kdf_root_chain_step(root_key: bytes, dh_output: bytes) -> tuple[bytes, bytes]:
    """
    Signal KDF_RK [spec 3.3]
    (root_key, dh_output) -> (new_root_key, chain_key)

    Uses HKDF-SHA256 with root_key as salt, output 64 bytes.
    First 32 bytes = new root key, next 32 bytes = chain key.
    """
    from app.crypto.signal.primitives import hkdf
    okm = hkdf(
        salt=root_key,
        input_key_material=dh_output,
        info=HKDF_INFO_ROOT_CHAIN,
        length=64,
    )
    return okm[:32], okm[32:]


def kdf_chain_key_step(chain_key: bytes) -> tuple[bytes, bytes]:
    """
    Signal KDF_CK [spec 3.3]
    chain_key -> (next_chain_key, message_key)

    Uses HMAC-SHA256 with chain_key as the key:
      next_chain_key = HMAC(chain_key, 0x01)
      message_key    = HMAC(chain_key, 0x02)
    """
    from cryptography.hazmat.primitives import hashes, hmac

    h = hmac.HMAC(chain_key, hashes.SHA256())
    h.update(b"\x01")
    next_chain_key = h.finalize()

    h = hmac.HMAC(chain_key, hashes.SHA256())
    h.update(b"\x02")
    message_key = h.finalize()

    return next_chain_key, message_key


# ==========================================================
# Message Key Derivation
# ==========================================================

def derive_message_keys(message_key: bytes) -> tuple[bytes, bytes, bytes]:
    """
    Derive (encryption_key, nonce, associated_data_key) from message key.

    Per Signal spec section 3.3:
      enc_key = HKDF(message_key, info="WhisperMessageKeys", len=80)
      -> [0:32]  = encryption key (AES-256)
      -> [32:64] = auth key     (HMAC)
      -> [64:80] = nonce        (for AEAD)

    We use the full 80 bytes: first 32 AES key, next 32 auth key,
    last 16 as nonce seed (first 12 used).
    """
    from app.crypto.signal.primitives import hkdf, HKDF_INFO_MESSAGE_KEYS

    okm = hkdf(
        salt=b"",
        input_key_material=message_key,
        info=HKDF_INFO_MESSAGE_KEYS,
        length=80,
    )
    return okm[:32], okm[32:64], okm[64:80]


# ==========================================================================
# Ratchet Types
# ==========================================================================

@dataclass
class Chain:
    """
    One chain in the ratchet (sending or receiving).
    Holds the current chain key and the message index counter.
    """
    key: bytes
    index: int = 0


@dataclass
class DHKeyPair:
    """A DH key pair with its serialized raw form."""
    private: object   # X25519PrivateKey
    public: object    # X25519PublicKey
    public_raw: bytes

    @classmethod
    def from_private_key(cls, private_key):
        public_key = private_key.public_key()
        return cls(
            private=private_key,
            public=public_key,
            public_raw=x25519_public_to_bytes(public_key),
        )

    @classmethod
    def new(cls) -> "DHKeyPair":
        private_key, _ = generate_x25519_keypair()
        return cls.from_private_key(private_key)


# ==========================================================================
# Ratchet State Dataclass
# ==========================================================================

@dataclass
class RatchetState:
    """
    Holds the entire state of a Double Ratchet session.

    Fields:
      root_key            : 32 bytes root key
      sending_chain       : sending chain key state (or None if not initialized)
      receiving_chain     : receiving chain key state (or None)
      our_dh_pair         : our current DH key pair (ratchet key)
      their_dh_public     : their current DH public key (raw bytes)
      skipped_message_keys: dict mapping (dh_public_raw, message_number) -> chain key
      associated_data     : immutable AD used in all AEAD operations
      max_skip            : maximum skipped message keys for DoS protection
    """

    root_key: bytes
    our_dh_pair: DHKeyPair
    their_dh_public: Optional[bytes] = None
    sending_chain: Optional[Chain] = None
    receiving_chain: Optional[Chain] = None
    skipped_message_keys: dict = field(default_factory=dict)
    associated_data: bytes = b""
    max_skip: int = 1000

    # ==========================================================
    # Serialization (for DB storage)
    # ==========================================================

    def to_dict(self) -> dict:
        return {
            "root_key": self.root_key.hex(),
            "our_dh_private": x25519_private_to_bytes(self.our_dh_pair.private).hex(),
            "our_dh_public": self.our_dh_pair.public_raw.hex(),
            "their_dh_public": self.their_dh_public.hex() if self.their_dh_public else None,
            "sending_chain": {
                "key": self.sending_chain.key.hex(),
                "index": self.sending_chain.index,
            } if self.sending_chain else None,
            "receiving_chain": {
                "key": self.receiving_chain.key.hex(),
                "index": self.receiving_chain.index,
            } if self.receiving_chain else None,
            "skipped_message_keys": {
                f"{k[0].hex()}:{k[1]}": v.hex()
                for k, v in self.skipped_message_keys.items()
            },
            "associated_data": self.associated_data.hex(),
            "max_skip": self.max_skip,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "RatchetState":
        return cls(
            root_key=bytes.fromhex(data["root_key"]),
            our_dh_pair=DHKeyPair(
                private=x25519_private_from_bytes(bytes.fromhex(data["our_dh_private"])),
                public=x25519_public_from_bytes(bytes.fromhex(data["our_dh_public"])),
                public_raw=bytes.fromhex(data["our_dh_public"]),
            ),
            their_dh_public=(
                bytes.fromhex(data["their_dh_public"]) if data.get("their_dh_public") else None
            ),
            sending_chain=(
                Chain(
                    key=bytes.fromhex(data["sending_chain"]["key"]),
                    index=data["sending_chain"]["index"],
                )
                if data.get("sending_chain") else None
            ),
            receiving_chain=(
                Chain(
                    key=bytes.fromhex(data["receiving_chain"]["key"]),
                    index=data["receiving_chain"]["index"],
                )
                if data.get("receiving_chain") else None
            ),
            skipped_message_keys={
                (
                    bytes.fromhex(k.split(":")[0]),
                    int(k.split(":")[1]),
                ): bytes.fromhex(v)
                for k, v in data.get("skipped_message_keys", {}).items()
            },
            associated_data=bytes.fromhex(data.get("associated_data", "")) if data.get("associated_data") else b"",
            max_skip=data.get("max_skip", 1000),
        )


# ==========================================================================
# Core Operations
# ==========================================================================

class DoubleRatchetCore:
    """
    Pure Double Ratchet operations, no persistence.

    This class implements the ratchet steps themselves:
      - initialize (with initial symmetric key from X3DH)
      - ratchet_step (DH ratchet, called when receiving a new DH public key)
      - deriving message keys, etc.

    It does NOT interact with the DB. Persistence is the job of the
    SignalSession service layer.
    """

    def __init__(
        self,
        root_key: bytes,
        associated_data: bytes,
        our_initial_dh_private=None,
        their_dh_public: Optional[bytes] = None,
    ):
        """
        Initialize a Double Ratchet core.

        root_key: initial root key (from X3DH output).
        associated_data: AD (identity keys, X3DH context) for AEAD.
        our_initial_dh_private: our first ratified DH key
            (if None, one is generated).
        their_dh_public: our peer's current DH public key
            (None until the first message arrives).
        """
        from app.crypto.signal.primitives import x25519_private_from_bytes

        if our_initial_dh_private is None:
            self.our_dh_pair = DHKeyPair.new()
        else:
            self.our_dh_pair = DHKeyPair.from_private_key(our_initial_dh_private)
        self.root_key = root_key
        self.associated_data = associated_data
        self.their_dh_public = their_dh_public  # DHr
        self.sending_chain = None  # CKs
        self.receiving_chain = None  # CKr
        self.skipped_message_keys = {}  # MKSKIPPED
        self.max_skip = 1000
        self.previous_sending_number = 0  # PN

    def state(self) -> RatchetState:
        """Export current state."""
        return RatchetState(
            root_key=self.root_key,
            our_dh_pair=self.our_dh_pair,
            their_dh_public=self.their_dh_public,
            sending_chain=self.sending_chain,
            receiving_chain=self.receiving_chain,
            skipped_message_keys=self.skipped_message_keys,
            associated_data=self.associated_data,
            max_skip=self.max_skip,
        )

    @classmethod
    def from_state(cls, state: "RatchetState") -> "DoubleRatchetCore":
        """Rebuild a core from a previously saved state."""
        core = cls.__new__(cls)
        core.root_key = state.root_key
        core.our_dh_pair = state.our_dh_pair
        core.their_dh_public = state.their_dh_public
        core.sending_chain = state.sending_chain
        core.receiving_chain = state.receiving_chain
        core.skipped_message_keys = dict(state.skipped_message_keys)
        core.associated_data = state.associated_data
        core.max_skip = state.max_skip
        core.previous_sending_number = 0
        return core

    # ------------------------------------------------------------------
    # Skip message keys (spec: SKIP_MESSAGE_KEYS)
    # ------------------------------------------------------------------

    def _skip_message_keys(self, until: int, dh_public: bytes) -> None:
        """
        Derive and store message keys for all chain indices between the
        current receiving index and `until` (exclusive), tagged with the
        DH public key that the messages arrived under.
        """
        chain = self.receiving_chain
        if chain is None:
            return
        if chain.index + self.max_skip < until:
            raise ValueError("Too many skipped messages (possible DoS)")
        while chain.index < until:
            next_ck, mk = kdf_chain_key_step(chain.key)
            chain.key = next_ck
            key = (dh_public, chain.index)
            if len(self.skipped_message_keys) >= self.max_skip:
                raise ValueError("Skipped message key storage full (possible DoS)")
            self.skipped_message_keys[key] = mk
            chain.index += 1

    # ------------------------------------------------------------------
    # DH ratchet (spec: DHRatchet)
    # ------------------------------------------------------------------

    def dh_ratchet(self, their_new_dh_public: bytes) -> None:
        """
        [Spec DHRatchet]
        1. Save old sending chain number as PN.
        2. Reset Ns/Nr.
        3. KDF_RK(RK, DH(DHs, DHr)) -> new receiving chain.
        4. Generate new DHs.
        5. KDF_RK(RK, DH(new DHs, DHr)) -> new sending chain.
        """
        self.previous_sending_number = (
            self.sending_chain.index if self.sending_chain else 0
        )
        self.sending_chain = None

        their_public_obj = x25519_public_from_bytes(their_new_dh_public)
        self.their_dh_public = their_new_dh_public

        # Step 3: root, receiving chain (uses OUR current DH pair)
        new_root1, receiving_ck = kdf_root_chain_step(
            self.root_key,
            x25519_dh(self.our_dh_pair.private, their_public_obj),
        )
        self.root_key = new_root1
        self.receiving_chain = Chain(key=receiving_ck, index=0)

        # Step 4: new DH pair for us
        self.our_dh_pair = DHKeyPair.new()

        # Step 5: root, sending chain (uses NEW DH pair)
        new_root2, sending_ck = kdf_root_chain_step(
            self.root_key,
            x25519_dh(self.our_dh_pair.private, their_public_obj),
        )
        self.root_key = new_root2
        self.sending_chain = Chain(key=sending_ck, index=0)

    # ------------------------------------------------------------------
    # Initialization (per spec Section 2.4)
    # ------------------------------------------------------------------

    def initialize_initiator(self) -> None:
        """
        Alice (initiator) initialization:
          DHs = our DH pair (given)
          DHr = their signed prekey (given as their_dh_public)
          RK, CKs = KDF_RK(SK, DH(DHs, DHr))
        """
        if self.their_dh_public is None:
            raise ValueError("Initiation requires their DH public key")
        their_public_obj = x25519_public_from_bytes(self.their_dh_public)
        new_root, sending_ck = kdf_root_chain_step(
            self.root_key,
            x25519_dh(self.our_dh_pair.private, their_public_obj),
        )
        self.root_key = new_root
        self.sending_chain = Chain(key=sending_ck, index=0)
        # DHr set, no receiving chain yet (we wait for their first message)

    def initialize_responder(self) -> None:
        """
        Bob (responder) initialization:
        DHs = our DH pair (given)
        DHr = Alice's DH   (from her first message header)
        RK, CKr = KDF_RK(SK, DH(DHs, DHr))
        """
        if self.their_dh_public is None:
            raise ValueError("Responder needs Alice's DH from first message")
        their_public_obj = x25519_public_from_bytes(self.their_dh_public)
        new_root, receiving_c = kdf_root_chain_step(
            self.root_key,
            x25519_dh(self.our_dh_pair.private, their_public_obj),
        )
        self.root_key = new_root
        self.receiving_chain = Chain(key=receiving_c, index=0)

    # ------------------------------------------------------------------
    # Message key derivation
    # ------------------------------------------------------------------

    def _next_sending_message_key(self):
        """Return (message_key, message_number) and advance sending chain."""
        chain = self.sending_chain
        if chain is None:
            raise ValueError("No sending chain")
        next_ck, mk = kdf_chain_key_step(chain.key)
        chain.key = next_ck
        idx = chain.index
        chain.index += 1
        return mk, idx

    def _receiving_message_key(self, index: int):
        """
        Return message key for a received index:
        - if it was stored as skipped: pop & return
        - if it is the current expected index: derive it, advance chain
        - otherwise: error (too old)
        """
        key = self.skipped_message_keys.pop((self.their_dh_public, index), None)
        if key is not None:
            return key
        chain = self.receiving_chain
        if chain is None or index != chain.index:
            raise ValueError(
                f"Message index {index} out of order (expected {chain.index if chain else -1})"
            )
        next_ck, mk = kdf_chain_key_step(chain.key)
        chain.key = next_ck
        chain.index += 1
        return mk

    # ------------------------------------------------------------------
    # Encrypt / Decrypt (per spec RatchetEncrypt / RatchetDecrypt)
    # ------------------------------------------------------------------

    def encrypt_message(self, plaintext: bytes) -> tuple[dict, bytes]:
        """
        RatchetEncrypt:
        - CKs, mk = KDF_CK(CKs)
        - H = (PN, Ns, DHs)
        - Ns += 1
        - C = AEAD(mk, plaintext, AD)
        """
        chain = self.sending_chain
        if chain is None:
            raise ValueError("No sending chain to encrypt from")
        next_ck, mk = kdf_chain_key_step(chain.key)
        chain.key = next_ck
        idx = chain.index
        chain.index += 1

        header = {
            "pn": self.previous_sending_number,
            "n": idx,
            "dh": self.our_dh_pair.public_raw.hex(),
        }
        enc_key, _, nonce_seed = derive_message_key(mk)
        ad_data = self.associated_data + self.our_dh_pair.public_raw
        ciphertext, nonce = aes_gcm_encrypt(
            enc_key,
            plaintext,
            ad_data,
            nonce_seed[:12],
        )
        return header, ciphertext + nonce

    def decrypt_message(self, header: dict, payload: bytes) -> bytes:
        """RatchetDecrypt (incl. DHRatchet when header DH is new)."""
        their_dh = bytes.fromhex(header["dh"])
        n = header["n"]

        if their_dh != self.their_dh_public:
            # new epoch: skip keys of the current receiving chain, then ratchet
            self._skip_message_keys(
                self.receiving_chain.index if self.receiving_chain else 0,
                self.their_dh_public,
            )
            self.dh_ratchet(their_dh)

        # Skip message keys for gaps within THIS receiving chain
        chain = self.receiving_chain
        self._skip_message_keys_dh(their_dh, n)

        mk = self._receiving_message_key(n)

        enc_key, _, nonce = derive_message_key(mk)
        ad_data = self.associated_data + their_dh
        nonce_bytes = payload[-12:]
        ciphertext = payload[:-12]
        return aes_gcm_decrypt(enc_key, ciphertext, ad_data, nonce_bytes)

    def _skip_message_keys_dh(self, dh_public: bytes, until: int) -> None:
        """Store keys for indices in the receiving chain up to `until`."""
        chain = self.receiving_chain
        if chain is None:
            raise ValueError("No receiving chain")
        if chain.index + self.max_skip < until:
            raise ValueError("Too many skipped messages (possible DoS)")
        while chain.index < until:
            next_ck, mk = kdf_chain_key_step(chain.key)
            chain.key = next_ck
            if len(self.skipped_message_keys) >= self.max_skip:
                raise ValueError("Skipped message key limit reached (possible DoS)")
            self.skipped_message_keys[(dh_public, chain.index)] = mk
            chain.index += 1


def derive_message_key(message_key: bytes) -> tuple[bytes, bytes, bytes]:
    """Wrapper for derive_keys(message_key) with clearer naming."""
    enc_key, auth_key, nonce_seed = derive_keys(message_key)
    return enc_key, auth_key, nonce_seed


def derive_keys(message_key: bytes) -> tuple[bytes, bytes, bytes]:
    """
    Derive (encryption_key, auth_key, nonce_seed) from message key.
    128-bit nonce: 96 bits for AES-GCM nonce, leaving 4 bytes unused.
    """
    from app.crypto.signal.primitives import hkdf

    okm = hkdf(
        salt=b"",
        input_key_material=message_key,
        info=b"WhisperMessageKeys",
        length=80,
    )
    enc_key = okm[:32]
    auth_key = okm[32:64]
    nonce_seed = okm[64:80]
    return enc_key, auth_key, nonce_seed