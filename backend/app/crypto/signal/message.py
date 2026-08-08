"""
Signal Protocol Message Envelope

The full wire format for a Signal message:

- If a session has NOT been established yet, the first message is an
  X3DH handshake message (PreKeyWhisperMessage) that carries all data
  needed by the receiver to compute the shared secret and initialize
  the ratchet.

- Once sessions exist, messages are regular Double Ratchet messages
  (WhisperMessage) with ratchet headers.

Envelope JSON schema:
{
  "type": "prekey" | "data",
  "version": 1,
  "device_id": "sender device id (uuid str)",
  "sender_id":  "sender user id (uuid str)",
  "x3dh": {                      # only for type=prekey
      "identity_key":  "b64",      # sender Ed25519 identity public
      "ephemeral_key": "b64",      # sender X25519 ephemeral public
      "prekey_id":     1           # signed prekey id used by receiver
      "one_time_prekey_id": 3      # OPK id used (optional)
  },
  "ratchet": {                   # Double Ratchet header
      "pn": 0,                     # previous sending chain length
      "n":  0,                     # message number in sending chain
      "dh": "hex"                  # sender's current DH public key
  },
  "ciphertext": "b64",           # AEAD payload (nonce + ct)
  "timestamp": 1750000000000
}
"""

import base64
import json
import time
from dataclasses import dataclass, field

from cryptography.hazmat.primitives.asymmetric import ed25519, x25519

from app.crypto.signal.primitives import (
    b64encode, b64decode,
    ed25519_public_to_bytes, ed25519_public_from_bytes,
    x25519_public_to_bytes, x25519_public_from_bytes,
)


# ==========================================================
# Exceptions
# ==========================================================

class SignalProtocolError(Exception):
    """Base error for Signal Protocol failures."""
    pass


class EnvelopeError(SignalProtocolError):
    """Malformed or unverifiable envelope."""
    pass


# ==========================================================
# Envelope
# ==========================================================

@dataclass
class SignalEnvelope:
    """A single wire message between two devices."""
    type: str                                   # "prekey" | "data"
    device_id: str                              # sender's device id
    sender_id: str                              # sender's user id
    ratchet_header: dict                        # {pn, n, dh(hex)}
    ciphertext: str                             # b64
    x3dh_info: dict | None = None               # only for "prekey" type

    def to_json(self) -> str:
        return json.dumps({
            "type": self.type,
            "version": 1,
            "device_id": self.device_id,
            "sender_id": self.sender_id,
            "x3dh": self.x3dh_info,
            "ratchet": self.ratchet_header,
            "ciphertext": self.ciphertext,
        })

    @classmethod
    def from_json(cls, raw: str) -> "SignalEnvelope":
        try:
            data = json.loads(raw)
            version = data.get("version", -1)
            if version != 1:
                raise EnvelopeError(f"Unsupported protocol version: {version}")
            x3dh = data.get("x3dh")
            return cls(
                type=data["type"],
                device_id=data["device_id"],
                sender_id=data["sender_id"],
                ratchet_header=data["ratchet"],
                ciphertext=data["ciphertext"],
                x3dh_info=x3dh if x3dh is not None else None,
            )
        except (json.JSONDecodeError, KeyError) as e:
            raise EnvelopeError(f"Malformed envelope: {e}") from e

    @classmethod
    def prekey(
        cls,
        device_id: str,
        sender_id: str,
        identity_public: ed25519.Ed25519PublicKey,
        x25519_identity_public: x25519.X25519PublicKey,
        ephemeral_public: x25519.X25519PublicKey,
        signed_prekey_id: int,
        one_time_prekey_id: int | None,
        ratchet_header: dict,
        ciphertext: bytes,
    ) -> "SignalEnvelope":
        """Build a prekey (handshake) envelope."""
        info = {
            "identity_key": b64encode(ed25519_public_to_bytes(identity_public)),
            "x25519_identity_key": b64encode(
                x25519_public_to_bytes(x25519_identity_public)
            ),
            "ephemeral_key": b64encode(x25519_public_to_bytes(ephemeral_public)),
            "signed_prekey_id": signed_prekey_id,
        }
        if one_time_prekey_id is not None:
            info["one_time_prekey_id"] = one_time_prekey_id
        return cls(
            type="prekey",
            device_id=device_id,
            sender_id=sender_id,
            ratchet_header=ratchet_header,
            ciphertext=b64encode(ciphertext),
            x3dh_info=info,
        )

    def to_bytes(self) -> bytes:
        return self.to_json().encode("utf-8")


# ============================================================================
# X3DH Handshake Message
# ============================================================================

def build_prekey_message(
    device_id: str,
    sender_id: str,
    our_identity_private: ed25519.Ed25519PrivateKey,
    our_ephemeral_private: x25519.X25519PrivateKey,
    ratchet_header: dict,
    ciphertext: bytes,
    signed_prekey_id: int,
    one_time_prekey_id: int | None = None,
) -> SignalEnvelope:
    """
    Build the X3DH initiation message (the first message in a session).

    Carries the sender's ephemeral key + identity so the recipient
    can complete X3DH and establish the session.
    """
    return SignalEnvelope.prekey(
        device_id=device_id,
        sender_id=sender_id,
        identity_public=our_identity_private.public_key(),
        x25519_identity_public=_derive_x25519_pub(our_identity_private),
        ephemeral_public=our_ephemeral_private.public_key(),
        signed_prekey_id=signed_prekey_id,
        one_time_prekey_id=one_time_prekey_id,
        ratchet_header=ratchet_header,
        ciphertext=ciphertext,
    )


def _derive_x25519_pub(identity_private: ed25519.Ed25519PrivateKey) -> x25519.X25519PublicKey:
    """Derive the X25519 public key from an Ed25519 identity private key."""
    from app.crypto.signal.x3dh import derive_x25519_from_ed25519
    return derive_x25519_from_ed25519(identity_private).public_key()


def parse_prekey_message(envelope: SignalEnvelope) -> dict:
    """Extract X3DH initiator data from a prekey envelope."""
    if envelope.type != "prekey" or not envelope.x3dh_info:
        raise EnvelopeError("Not a prekey message")
    info = envelope.x3dh_info
    return {
        "identity_key": ed25519_public_from_bytes(b64decode(info["identity_key"])),
        "x25519_identity_key": x25519_public_from_bytes(
            b64decode(info["x25519_identity_key"])
        ),
        "ephemeral_key": x25519_public_from_bytes(b64decode(info["ephemeral_key"])),
        "signed_prekey_id": info["signed_prekey_id"],
        "one_time_prekey_id": info.get("one_time_prekey_id"),
    }