"""
Signal Protocol Cryptographic Primitives

Low-level cryptographic operations using the `cryptography` library.
All keys are handled as raw bytes (32 bytes for X25519/Ed25519, 32 bytes for symmetric keys).
Encoding/decoding to base64 happens at the API boundary.
"""

import base64
import os

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, hmac, serialization
from cryptography.hazmat.primitives.asymmetric import ed25519, x25519
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

# ==========================================================
# Constants
# ==========================================================

# Signal Protocol constants
CURVE25519_KEY_SIZE = 32
ED25519_KEY_SIZE = 32
ED25519_SIGNATURE_SIZE = 64
AES_KEY_SIZE = 32
AES_NONCE_SIZE = 12
HMAC_KEY_SIZE = 32

# HKDF info strings (per Signal Protocol spec)
HKDF_INFO_MESSAGE_KEYS = b"WhisperMessageKeys"
HKDF_INFO_ROOT_CHAIN = b"WhisperRootChain"
HKDF_INFO_CHAIN_KEY = b"WhisperChainKey"
HKDF_INFO_X3DH = b"WhisperX3DH"

# AD (Associated Data) for AEAD
AD_INITIATOR = b"initiator"
AD_RECEIVER = b"receiver"


# ==========================================================
# Encoding Helpers
# ==========================================================

def b64encode(data: bytes) -> str:
    """Encode bytes to base64 string."""
    return base64.b64encode(data).decode("ascii")


def b64decode(data: str) -> bytes:
    """Decode base64 string to bytes."""
    return base64.b64decode(data.encode("ascii"))


def ensure_bytes(data: str | bytes) -> bytes:
    """Ensure input is bytes."""
    if isinstance(data, str):
        return b64decode(data)
    return data


# ==========================================================
# X25519 (DH) Operations
# ==========================================================

def generate_x25519_keypair() -> tuple[x25519.X25519PrivateKey, x25519.X25519PublicKey]:
    """Generate a new X25519 key pair."""
    private_key = x25519.X25519PrivateKey.generate()
    public_key = private_key.public_key()
    return private_key, public_key


def x25519_private_to_bytes(private_key: x25519.X25519PrivateKey) -> bytes:
    """Serialize X25519 private key to raw bytes (32 bytes)."""
    return private_key.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )


def x25519_public_to_bytes(public_key: x25519.X25519PublicKey) -> bytes:
    """Serialize X25519 public key to raw bytes (32 bytes)."""
    return public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )


def x25519_private_from_bytes(data: bytes) -> x25519.X25519PrivateKey:
    """Load X25519 private key from raw bytes (32 bytes)."""
    return x25519.X25519PrivateKey.from_private_bytes(data)


def x25519_public_from_bytes(data: bytes) -> x25519.X25519PublicKey:
    """Load X25519 public key from raw bytes (32 bytes)."""
    return x25519.X25519PublicKey.from_public_bytes(data)


def x25519_dh(private_key: x25519.X25519PrivateKey, peer_public_key: x25519.X25519PublicKey) -> bytes:
    """Perform X25519 Diffie-Hellman key agreement."""
    return private_key.exchange(peer_public_key)


# ==========================================================
# Ed25519 (Signature) Operations
# ==========================================================

def generate_ed25519_keypair() -> tuple[ed25519.Ed25519PrivateKey, ed25519.Ed25519PublicKey]:
    """Generate a new Ed25519 key pair."""
    private_key = ed25519.Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    return private_key, public_key


def ed25519_private_to_bytes(private_key: ed25519.Ed25519PrivateKey) -> bytes:
    """Serialize Ed25519 private key to raw bytes (32 bytes)."""
    return private_key.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )


def ed25519_public_to_bytes(public_key: ed25519.Ed25519PublicKey) -> bytes:
    """Serialize Ed25519 public key to raw bytes (32 bytes)."""
    return public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )


def ed25519_private_from_bytes(data: bytes) -> ed25519.Ed25519PrivateKey:
    """Load Ed25519 private key from raw bytes (32 bytes)."""
    return ed25519.Ed25519PrivateKey.from_private_bytes(data)


def ed25519_public_from_bytes(data: bytes) -> ed25519.Ed25519PublicKey:
    """Load Ed25519 public key from raw bytes (32 bytes)."""
    return ed25519.Ed25519PublicKey.from_public_bytes(data)


def ed25519_sign(private_key: ed25519.Ed25519PrivateKey, message: bytes) -> bytes:
    """Sign message with Ed25519 private key."""
    return private_key.sign(message)


def ed25519_verify(public_key: ed25519.Ed25519PublicKey, signature: bytes, message: bytes) -> bool:
    """Verify Ed25519 signature."""
    try:
        public_key.verify(signature, message)
        return True
    except InvalidSignature:
        return False


# ==========================================================
# HKDF Key Derivation
# ==========================================================

def hkdf_extract(salt: bytes, input_key_material: bytes) -> bytes:
    """HKDF-Extract: derive a pseudorandom key from input key material."""
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        info=b"",
    )
    return hkdf.derive(input_key_material)


def hkdf_expand(pseudorandom_key: bytes, info: bytes, length: int = 32) -> bytes:
    """HKDF-Expand: expand a pseudorandom key into output key material."""
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=length,
        salt=b"",
        info=info,
    )
    return hkdf.derive(pseudorandom_key)


def hkdf(salt: bytes, input_key_material: bytes, info: bytes, length: int = 32) -> bytes:
    """Full HKDF: extract then expand."""
    prk = hkdf_extract(salt, input_key_material)
    return hkdf_expand(prk, info, length)


# Signal-specific HKDF functions

def kdf_root_chain(root_key: bytes, dh_output: bytes) -> tuple[bytes, bytes]:
    """
    Signal Root Chain KDF.

    Input: root_key (32 bytes), DH output (32 bytes)
    Output: (new_root_key, chain_key) each 32 bytes
    """
    # HKDF with root_key as salt, dh_output as IKM
    output = hkdf(root_key, dh_output, HKDF_INFO_ROOT_CHAIN, 64)
    new_root_key = output[:32]
    chain_key = output[32:]
    return new_root_key, chain_key


def kdf_chain_key(chain_key: bytes) -> tuple[bytes, bytes]:
    """
    Signal Chain Key KDF.

    Input: chain_key (32 bytes)
    Output: (next_chain_key, message_key) each 32 bytes
    """
    # HMAC-SHA256 with chain_key as key, 0x01 as message for next chain key
    h = hmac.HMAC(chain_key, hashes.SHA256())
    h.update(b"\x01")
    next_chain_key = h.finalize()

    # HMAC-SHA256 with chain_key as key, 0x02 as message for message key
    h = hmac.HMAC(chain_key, hashes.SHA256())
    h.update(b"\x02")
    message_key = h.finalize()

    return next_chain_key, message_key


# ==========================================================
# AES-256-GCM (AEAD)
# ==========================================================

def aes_gcm_encrypt(key: bytes, plaintext: bytes, associated_data: bytes, nonce: bytes | None = None) -> tuple[bytes, bytes]:
    """
    Encrypt with AES-256-GCM.

    Returns: (ciphertext, nonce)
    """
    if nonce is None:
        nonce = os.urandom(AES_NONCE_SIZE)

    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(nonce, plaintext, associated_data)

    return ciphertext, nonce


def aes_gcm_decrypt(key: bytes, ciphertext: bytes, associated_data: bytes, nonce: bytes) -> bytes:
    """Decrypt with AES-256-GCM."""
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, ciphertext, associated_data)


# ==========================================================
# Key Generation Helpers
# ==========================================================

def generate_symmetric_key() -> bytes:
    """Generate a random 32-byte symmetric key."""
    return os.urandom(AES_KEY_SIZE)


def generate_nonce() -> bytes:
    """Generate a random 12-byte nonce for AES-GCM."""
    return os.urandom(AES_NONCE_SIZE)


# ==========================================================
# X3DH Key Agreement
# ==========================================================

def x3dh_initiate(
    # Our keys
    our_identity_private: ed25519.Ed25519PrivateKey,
    our_ephemeral_private: x25519.X25519PrivateKey,
    # Their keys (from key bundle)
    their_identity_public: ed25519.Ed25519PublicKey,
    their_signed_prekey_public: x25519.X25519PublicKey,
    their_signed_prekey_signature: bytes,
    their_one_time_prekey_public: x25519.X25519PublicKey | None = None,
) -> tuple[bytes, dict]:
    """
    Perform X3DH key agreement as the initiator (Alice).

    Returns: (shared_secret, associated_data_dict)

    Associated data contains all public keys used for verification.
    """
    # Verify the signed prekey signature
    spk_bytes = x25519_public_to_bytes(their_signed_prekey_public)
    if not ed25519_verify(their_identity_public, their_signed_prekey_signature, spk_bytes):
        raise ValueError("Invalid signed prekey signature")

    # DH1 = DH(our_ephemeral, their_signed_prekey)
    x25519_dh(our_ephemeral_private, their_signed_prekey_public)

    # DH2 = DH(our_identity, their_signed_prekey)
    # Note: Identity key is Ed25519, need to convert to X25519 for DH
    # In Signal, identity key is Ed25519 but used for X25519 DH via key conversion
    # For simplicity, we use a separate X25519 identity key or derive
    # Here we'll use a separate X25519 identity key pair
    # Actually, Signal uses the same key material - Ed25519 identity key
    # But for DH, we need X25519. The conversion is:
    # X25519 private = HKDF(Ed25519 private, info="X25519")
    # This is a simplification - in production use libsignal
    raise NotImplementedError("X3DH with Ed25519 identity keys requires key conversion. Use separate X25519 identity keys for DH.")

    # The full X3DH:
    # DH1 = DH(EKa, SPKb)
    # DH2 = DH(IKa, SPKb)  # IKa is Ed25519, need conversion
    # DH3 = DH(EKa, IKb)   # IKb is Ed25519, need conversion
    # DH4 = DH(EKa, OPKb)  # if OPKb exists
    # SK = KDF(DH1 || DH2 || DH3 || DH4)

    # For now, we'll use a simplified version with separate X25519 identity keys
    # This is handled in x3dh.py with proper key management

    return b"", {}


def x3dh_receive(
    # Their ephemeral public key (from message)
    their_ephemeral_public: x25519.X25519PublicKey,
    # Their identity public key
    their_identity_public: ed25519.Ed25519PublicKey,
    # Our keys
    our_identity_private: ed25519.Ed25519PrivateKey,
    our_signed_prekey_private: x25519.X25519PrivateKey,
    our_one_time_prekey_private: x25519.X25519PrivateKey | None = None,
) -> tuple[bytes, dict]:
    """
    Perform X3DH key agreement as the receiver (Bob).

    Returns: (shared_secret, associated_data_dict)
    """
    raise NotImplementedError("See x3dh.py for full implementation with proper key types")


# ==========================================================
# Utility
# ==========================================================

def constant_time_compare(a: bytes, b: bytes) -> bool:
    """Constant-time comparison to prevent timing attacks."""
    if len(a) != len(b):
        return False
    result = 0
    for x, y in zip(a, b, strict=False):
        result |= x ^ y
    return result == 0
