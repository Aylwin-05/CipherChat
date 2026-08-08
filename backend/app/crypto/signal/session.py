"""
Signal Session Manager

Ties together X3DH + Double Ratchet + Envelope into a single API
used by the backend services and message routes.

Responsibilities:
- Create a session as the initiator (Alice): fetch peer's key bundle,
  run X3DH, initialize ratchet, produce the first prekey message.
- Create a session as the responder (Bob): parse the prekey message,
  run X3DH, initialize ratchet, save session state.
- Encrypt a message in an established session.
- Decrypt a first (prekey) message as responder.
- Decrypt a regular (data) message in an established session.

Associated data (AD) for AEAD:
  AD = initiator_identity_public || responder_identity_public
  (both raw Ed25519 public keys; initiator first, per Signal spec)
"""

from dataclasses import dataclass
from typing import Optional

from app.crypto.signal.primitives import (
    b64encode,
    b64decode,
    ed25519_public_to_bytes,
    ed25519_private_from_bytes,
    ed25519_public_from_bytes,
    x25519_public_to_bytes,
    x25519_public_from_bytes,
    x25519_private_from_bytes,
    generate_x25519_keypair,
)
from app.crypto.signal.x3dh import (
    x3dh_initiate,
    x3dh_receive,
    X3DHOutput,
    derive_x25519_from_ed25519,
)
from app.crypto.signal.double_ratchet import DoubleRatchetCore, RatchetState
from app.crypto.signal.message import (
    SignalEnvelope,
    EnvelopeError,
    parse_prekey_message,
    SignalProtocolError,
)


# ==========================================================
# Errors
# ==========================================================

class SessionError(SignalProtocolError):
    pass


class SessionNotFoundError(SessionError):
    pass


# ==========================================================
# Session Store Protocol
# ==========================================================

class SessionStore:
    """
    Abstract store for session state. The persistence layer (DB) must
    implement these methods; an InMemorySessionStore is provided for
    tests and single-process dev.
    """

    async def get(
        self,
        our_device_id: str,
        remote_device_id: str,
        conversation_id: str,
    ) -> Optional[RatchetState]:
        raise NotImplementedError

    async def save(
        self,
        our_device_id: str,
        remote_device_id: str,
        conversation_id: str,
        state: RatchetState,
    ) -> None:
        raise NotImplementedError

    async def delete(
        self,
        our_device_id: str,
        remote_device_id: str,
        conversation_id: str,
    ) -> None:
        raise NotImplementedError


class InMemorySessionStore(SessionStore):
    """Simple dict-backed store for tests/dev."""
    def __init__(self):
        self._sessions: dict[tuple, RatchetState] = {}

    async def get(self, our_device_id, remote_device_id, conversation_id):
        return self._sessions.get(
            (our_device_id, remote_device_id, conversation_id)
        )

    async def save(self, our_device_id, remote_device_id, conversation_id, state):
        self._sessions[
            (our_device_id, remote_device_id, conversation_id)
        ] = state

    async def delete(self, our_device_id, remote_device_id, conversation_id):
        self._sessions.pop(
            (our_device_id, remote_device_id, conversation_id), None
        )


# ==========================================================
# Result
# ==========================================================

@dataclass
class SessionResult:
    plaintext: bytes = b""
    sender_device_id: str = ""
    new_session: bool = False


# ==========================================================
# Session Manager
# ==========================================================

class SignalSessionManager:
    """
    Orchestrates Signal sessions across devices.
    """

    def __init__(self, store: SessionStore):
        self.store = store

    # ==========================================================
    # Initiator (Alice) - first message
    # ==========================================================

    async def encrypt_first(
        self,
        *,
        our_device_id: str,
        our_user_id: str,
        our_identity_private: bytes,          # raw Ed25519 private
        their_device_id: str,
        their_bundle: dict,                   # key bundle dict from server
        conversation_id: str,
        plaintext: bytes,
    ) -> SignalEnvelope:
        """
        Build the FIRST message to a remote device (registers the session).

        their_bundle (what the server stores under the remote's device):
            {
              "identity_key": b64,        # Ed25519 pub
              "x25519_identity_key": b64,
              "signed_prekey": {"key_id": int, "public_key": b64, "signature": b64},
              "one_time_prekeys": [{"key_id": int, "public_key": b64}, ...],
            }
        """
        # --- load our identity & make ephemeral ---
        our_ik_priv = ed25519_private_from_bytes(our_identity_private)
        our_ek_priv, _ = generate_x25519_keypair()

        # --- parse their bundle ---
        try:
            their_ik_pub = ed25519_public_from_bytes(
                b64decode(their_bundle["identity_key"])
            )
            their_x_pub = x25519_public_from_bytes(
                b64decode(their_bundle["x25519_identity_key"])
            )
            spk = their_bundle["signed_prekey"]
            spk_pub = x25519_public_from_bytes(b64decode(spk["public_key"]))
            spk_id = spk["key_id"]
            spk_sig = b64decode(spk["signature"])
        except (KeyError, ValueError) as e:
            raise SessionError(f"Malformed remote key bundle: {e}") from e

        opk = None
        opk_id = None
        if their_bundle.get("one_time_prekeys"):
            first = their_bundle["one_time_prekeys"][0]
            try:
                opk = x25519_public_from_bytes(b64decode(first["public_key"]))
                opk_id = first["key_id"]
            except (KeyError, ValueError):
                pass

        # --- X3DH as initiator ---
        x3dh: X3DHOutput = x3dh_initiate(
            our_identity_private=our_ik_priv,
            our_ephemeral_private=our_ek_priv,
            their_identity_public=their_ik_pub,
            their_x25519_identity_public=their_x_pub,
            their_signed_prekey_public=spk_pub,
            their_signed_prekey_signature=spk_sig,
            their_signed_prekey_id=spk_id,
            their_one_time_prekey_public=opk,
            their_one_time_prekey_id=opk_id,
        )

        # --- AD: initiator identity || responder identity ---
        ad = build_associated_data(
            our_ik_priv.public_key(),
            their_ik_pub,
        )

        # --- ratchet init (initiator timeline) ---
        # Alice's initial ratchet DH pair = her X3DH ephemeral key pair
        ratchet = DoubleRatchetCore(
            x3dh.shared_secret,
            ad,
            our_initial_dh_private=our_ek_priv,
        )
        ratchet.their_dh_public = x25519_public_to_bytes(spk_pub)
        ratchet.initialize_initiator()

        # --- encrypt the first payload ---
        header, payload = ratchet.encrypt_message(plaintext)

        # --- save session state ---
        await self.store.save(
            our_device_id, their_device_id, conversation_id, ratchet.state()
        )

        # --- build prekey envelope carrying our X3DH data ---
        env = SignalEnvelope.prekey(
            device_id=our_device_id,
            sender_id=our_user_id or our_device_id,
            identity_public=our_ik_priv.public_key(),
            x25519_identity_public=derive_x25519_from_ed25519(
                our_ik_priv
            ).public_key(),
            ephemeral_public=our_ek_priv.public_key(),
            signed_prekey_id=spk_id,
            one_time_prekey_id=opk_id,
            ratchet_header=header,
            ciphertext=payload,
        )
        return env

    # ==========================================================
    # Encrypt - established session
    # ==========================================================

    async def encrypt(
        self,
        *,
        our_device_id: str,
        our_user_id: str,
        remote_device_id: str,
        conversation_id: str,
        plaintext: bytes,
    ) -> SignalEnvelope:
        """Encrypt a message in an existing session."""
        state = await self.store.get(
            our_device_id, remote_device_id, conversation_id
        )
        if state is None:
            raise SessionNotFoundError(
                "No session with remote device; use encrypt_first"
            )
        ratchet = DoubleRatchetCore.from_state(state)
        header, payload = ratchet.encrypt_message(plaintext)
        await self.store.save(
            our_device_id, remote_device_id, conversation_id, ratchet.state()
        )
        return SignalEnvelope(
            type="data",
            device_id=our_device_id,
            sender_id=our_user_id or our_device_id,
            ratchet_header=header,
            ciphertext=b64encode(payload),
        )

    # ==========================================================
    # Responder (Bob) - first message
    # ==========================================================

    async def decrypt_first(
        self,
        *,
        envelope: SignalEnvelope,
        our_device_id: str,
        our_user_id: str,
        our_identity_private: bytes,              # raw Ed25519 private
        signed_prekey: dict,                      # {"key_id": int, "private_key": b64}
        one_time_prekey: Optional[dict],          # same or None
        conversation_id: str,
    ) -> SessionResult:
        """
        Bob: receives the first prekey message from Alice.
        Completes X3DH, initializes the ratchet, decrypts the payload,
        and stores the session state.
        """
        if envelope.type != "prekey" or not envelope.x3dh_info:
            raise SessionError("Not a handshake (prekey) envelope")

        info = envelope.x3dh_info
        try:
            their_ik_pub = ed25519_public_from_bytes(
                b64decode(info["identity_key"])
            )
            their_x_pub = x25519_public_from_bytes(
                b64decode(info["x25519_identity_key"])
            )
            their_ek_pub = x25519_public_from_bytes(
                b64decode(info["ephemeral_key"])
            )
        except (KeyError, ValueError) as exc:
            raise EnvelopeError(f"Invalid handshake data: {exc}") from exc

        our_ik_priv = ed25519_private_from_bytes(our_identity_private)
        spk_priv = x25519_private_from_bytes(
            b64decode(signed_prekey["private_key"])
        )

        otpk_priv = None
        if one_time_prekey is not None:
            otpk_priv = x25519_private_from_bytes(
                b64decode(one_time_prekey["private_key"])
            )

        # --- X3DH as responder ---
        x3dh: X3DHOutput = x3dh_receive(
            their_ephemeral_public=their_ek_pub,
            their_identity_public=their_ik_pub,
            their_x25519_identity_public=their_x_pub,
            our_identity_private=our_ik_priv,
            our_signed_prekey_private=spk_priv,
            our_signed_prekey_id=signed_prekey["key_id"],
            our_one_time_prekey_private=otpk_priv,
            our_one_time_prekey_id=(
                one_time_prekey["key_id"] if one_time_prekey else None
            ),
        )

        # --- AD: initiator (Alice) first ---
        ad = build_associated_data(
            their_ik_pub,
            our_ik_priv.public_key(),
        )

        # --- ratchet init (responder) ---
        # Bob's initial ratchet DH pair = his signed prekey pair.
        # We do not pre-set their_dh_public: the first decrypt triggers the
        # full DHRatchet (KDF with our SPK + their EK for the receiving
        # chain, then a fresh DH pair for our sending chain).
        ratchet = DoubleRatchetCore(
            x3dh.shared_secret,
            ad,
            our_initial_dh_private=spk_priv,
        )

        # --- decrypt the first payload ---
        plaintext = ratchet.decrypt_message(
            envelope.ratchet_header,
            b64decode(envelope.ciphertext),
        )

        await self.store.save(
            our_device_id, envelope.device_id, conversation_id,
            ratchet.state(),
        )
        return SessionResult(
            plaintext=plaintext,
            sender_device_id=envelope.device_id,
            new_session=True,
        )

    # ==========================================================
    # Decrypt - established session
    # ==========================================================

    async def decrypt(
        self,
        *,
        envelope: SignalEnvelope,
        our_device_id: str,
        conversation_id: str,
    ) -> SessionResult:
        """Decrypt a regular data message in an established session."""
        if envelope.type != "data":
            raise SessionError("Not a data envelope")
        state = await self.store.get(
            our_device_id, envelope.device_id, conversation_id
        )
        if state is None:
            raise SessionNotFoundError("No session with sender device")
        ratchet = DoubleRatchetCore.from_state(state)
        plaintext = ratchet.decrypt_message(
            envelope.ratchet_header,
            b64decode(envelope.ciphertext),
        )
        await self.store.save(
            our_device_id, envelope.device_id, conversation_id,
            ratchet.state(),
        )
        return SessionResult(
            plaintext=plaintext,
            sender_device_id=envelope.device_id,
        )


# ==========================================================
# Helpers
# ==========================================================

def build_associated_data(
    initiator_identity: object,     # Ed25519PublicKey
    responder_identity: object,     # Ed25519PublicKey
) -> bytes:
    """AD = initiator IK || responder IK (raw public keys)."""
    return (
        ed25519_public_to_bytes(initiator_identity)
        + ed25519_public_to_bytes(responder_identity)
    )