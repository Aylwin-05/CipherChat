"""
X3DH (Extended Triple Diffie-Hellman) Key Agreement

Per Signal Protocol specification:
https://signal.org/docs/specifications/x3dh/

Key hierarchy:
- Identity Key (IK): Ed25519, long-term
- Signed PreKey (SPK): X25519, medium-term, signed by IK
- One-Time PreKeys (OPK): X25519, ephemeral
- Ephemeral Key (EK): X25519, per-session

X3DH computes 4 DH shared secrets:
  DH1 = DH(EK_A, SPK_B)
  DH2 = DH(IK_A, SPK_B)  -- but IK is Ed25519!
  DH3 = DH(EK_A, IK_B)   -- IK is Ed25519!
  DH4 = DH(EK_A, OPK_B)  -- if OPK exists

Solution: Use separate X25519 identity keys for DH, derived from Ed25519 identity keys.
Or simpler: Use X25519 for everything (as libsignal does for some implementations).

For this implementation, we'll use a simplified but secure approach:
- Each device has an X25519 identity key pair (separate from Ed25519 signing key)
- Or we derive X25519 from Ed25519 using HKDF

We'll go with: X25519 identity key = HKDF(Ed25519 private, "X25519-Identity")
"""

from dataclasses import dataclass

from app.crypto.signal.primitives import (
    CURVE25519_KEY_SIZE,
    b64decode,
    b64encode,
    ed25519_private_to_bytes,
    ed25519_public_from_bytes,
    ed25519_public_to_bytes,
    ed25519_sign,
    ed25519_verify,
    hkdf,
    x25519_dh,
    x25519_private_from_bytes,
    x25519_public_from_bytes,
    x25519_public_to_bytes,
)
from cryptography.hazmat.primitives.asymmetric import ed25519, x25519

# ==========================================================
# Constants
# ==========================================================

# HKDF info for deriving X25519 identity key from Ed25519
HKDF_INFO_IDENTITY_TO_X25519 = b"Signal-Identity-To-X25519"
HKDF_INFO_X3DH = b"WhisperX3DH"


# ==========================================================
# Key Derivation: Ed25519 -> X25519
# ==========================================================

def derive_x25519_from_ed25519(ed25519_private: ed25519.Ed25519PrivateKey) -> x25519.X25519PrivateKey:
    """
    Derive an X25519 private key from an Ed25519 private key.

    This allows using a single Ed25519 identity key for both signing and DH.
    Per Signal spec: X25519_private = HKDF(Ed25519_private, info="X25519-Identity")
    """
    ed_priv_bytes = ed25519_private_to_bytes(ed25519_private)
    x25519_priv_bytes = hkdf(
        salt=b"",
        input_key_material=ed_priv_bytes,
        info=HKDF_INFO_IDENTITY_TO_X25519,
        length=CURVE25519_KEY_SIZE,
    )
    return x25519_private_from_bytes(x25519_priv_bytes)


def get_x25519_identity_public(ed25519_private: ed25519.Ed25519PrivateKey) -> x25519.X25519PublicKey:
    """Get the X25519 public key derived from Ed25519 identity key."""
    x25519_priv = derive_x25519_from_ed25519(ed25519_private)
    return x25519_priv.public_key()


# ==========================================================
# Key Bundle (what's published to server)
# ==========================================================

@dataclass
class KeyBundle:
    """Public key bundle for a device, published to server for X3DH."""
    device_id: str
    identity_key: str          # Ed25519 public key (base64)
    x25519_identity_key: str   # X25519 public key derived from Ed25519 (base64)
    signed_prekey: 'SignedPreKeyBundle'
    one_time_prekeys: list['OneTimePreKeyBundle']  # list of OPK bundles

    def to_dict(self) -> dict:
        return {
            "device_id": self.device_id,
            "identity_key": self.identity_key,
            "x25519_identity_key": self.x25519_identity_key,
            "signed_prekey": self.signed_prekey.to_dict(),
            "one_time_prekeys": [opk.to_dict() for opk in self.one_time_prekeys],
        }


@dataclass
class SignedPreKeyBundle:
    key_id: int
    public_key: str            # X25519 public key (base64)
    signature: str             # Ed25519 signature of public_key (base64)

    def to_dict(self) -> dict:
        return {
            "key_id": self.key_id,
            "public_key": self.public_key,
            "signature": self.signature,
        }


@dataclass
class OneTimePreKeyBundle:
    key_id: int
    public_key: str            # X25519 public key (base64)

    def to_dict(self) -> dict:
        return {
            "key_id": self.key_id,
            "public_key": self.public_key,
        }


# ==========================================================
# Create Key Bundle from Device Keys
# ==========================================================

def create_key_bundle(
    device_id: str,
    identity_private: ed25519.Ed25519PrivateKey,
    signed_prekey_private: x25519.X25519PrivateKey,
    signed_prekey_id: int,
    one_time_prekeys: list[tuple[int, x25519.X25519PrivateKey]],  # list of (key_id, private_key)
) -> KeyBundle:
    """
    Create a public key bundle from device's private keys.

    The bundle is what gets published to the server for other users to fetch.
    """
    identity_public = identity_private.public_key()
    x25519_identity_public = get_x25519_identity_public(identity_private)
    signed_prekey_public = signed_prekey_private.public_key()

    # Sign the signed prekey with identity key
    spk_bytes = x25519_public_to_bytes(signed_prekey_public)
    signature = ed25519_sign(identity_private, spk_bytes)

    spk_bundle = SignedPreKeyBundle(
        key_id=signed_prekey_id,
        public_key=b64encode(spk_bytes),
        signature=b64encode(signature),
    )

    opk_bundles = []
    for key_id, opk_private in one_time_prekeys:
        opk_public = opk_private.public_key()
        opk_bundles.append(OneTimePreKeyBundle(
            key_id=key_id,
            public_key=b64encode(x25519_public_to_bytes(opk_public)),
        ))

    return KeyBundle(
        device_id=device_id,
        identity_key=b64encode(ed25519_public_to_bytes(identity_public)),
        x25519_identity_key=b64encode(x25519_public_to_bytes(x25519_identity_public)),
        signed_prekey=spk_bundle,
        one_time_prekeys=opk_bundles,
    )


# ==========================================================
# X3DH Key Agreement
# ==========================================================

@dataclass
class X3DHOutput:
    """Result of X3DH key agreement."""
    shared_secret: bytes           # 32 bytes - the agreed secret
    associated_data: bytes         # For session initialization
    used_one_time_prekey_id: int | None = None


def x3dh_initiate(
    # Initiator's keys (Alice)
    our_identity_private: ed25519.Ed25519PrivateKey,
    our_ephemeral_private: x25519.X25519PrivateKey,
    # Responder's key bundle (Bob)
    their_identity_public: ed25519.Ed25519PublicKey,
    their_x25519_identity_public: x25519.X25519PublicKey,
    their_signed_prekey_public: x25519.X25519PublicKey,
    their_signed_prekey_signature: bytes,
    their_signed_prekey_id: int,
    their_one_time_prekey_public: x25519.X25519PublicKey | None = None,
    their_one_time_prekey_id: int | None = None,
) -> X3DHOutput:
    """
    Perform X3DH as the initiator (Alice).

    Computes:
      DH1 = DH(EK_A, SPK_B)
      DH2 = DH(IK_A_X25519, SPK_B)
      DH3 = DH(EK_A, IK_B_X25519)
      DH4 = DH(EK_A, OPK_B)  [if OPK exists]

    SK = KDF(DH1 || DH2 || DH3 || DH4)
    """
    # Verify the signed prekey signature
    spk_bytes = x25519_public_to_bytes(their_signed_prekey_public)
    if not ed25519_verify(their_identity_public, their_signed_prekey_signature, spk_bytes):
        raise ValueError("Invalid signed prekey signature")

    # DH1 = DH(EK_A, SPK_B)
    dh1 = x25519_dh(our_ephemeral_private, their_signed_prekey_public)

    # DH2 = DH(IK_A_X25519, SPK_B)
    our_x25519_identity = derive_x25519_from_ed25519(our_identity_private)
    dh2 = x25519_dh(our_x25519_identity, their_signed_prekey_public)

    # DH3 = DH(EK_A, IK_B_X25519)
    dh3 = x25519_dh(our_ephemeral_private, their_x25519_identity_public)

    # DH4 = DH(EK_A, OPK_B) if OPK exists
    dh4 = b""
    if their_one_time_prekey_public is not None:
        dh4 = x25519_dh(our_ephemeral_private, their_one_time_prekey_public)

    # Concatenate DH outputs
    dh_combined = dh1 + dh2 + dh3 + dh4

    # Derive shared secret: SK = HKDF(salt=0, IKM=dh_combined, info="WhisperX3DH")
    shared_secret = hkdf(
        salt=b"\x00" * 32,
        input_key_material=dh_combined,
        info=HKDF_INFO_X3DH,
        length=32,
    )

    # Associated data for session initialization
    # Contains all public keys used
    ad = (
        x25519_public_to_bytes(our_ephemeral_private.public_key()) +
        spk_bytes +
        x25519_public_to_bytes(their_x25519_identity_public)
    )
    if their_one_time_prekey_public:
        ad += x25519_public_to_bytes(their_one_time_prekey_public)

    return X3DHOutput(
        shared_secret=shared_secret,
        associated_data=ad,
        used_one_time_prekey_id=their_one_time_prekey_id,
    )


def x3dh_receive(
    # Initiator's ephemeral public key (from message)
    their_ephemeral_public: x25519.X25519PublicKey,
    # Their identity public key (Ed25519 for verification)
    their_identity_public: ed25519.Ed25519PublicKey,
    # Their X25519 identity public key (from their key bundle or message)
    their_x25519_identity_public: x25519.X25519PublicKey,
    # Responder's keys (Bob)
    our_identity_private: ed25519.Ed25519PrivateKey,
    our_signed_prekey_private: x25519.X25519PrivateKey,
    our_signed_prekey_id: int,
    our_one_time_prekey_private: x25519.X25519PrivateKey | None = None,
    our_one_time_prekey_id: int | None = None,
) -> X3DHOutput:
    """
    Perform X3DH as the receiver (Bob).

    Computes same DH values as initiator:
      DH1 = DH(SPK_B, EK_A)
      DH2 = DH(SPK_B, IK_A_X25519)
      DH3 = DH(IK_B_X25519, EK_A)
      DH4 = DH(OPK_B, EK_A)  [if OPK exists]
    """
    # DH1 = DH(SPK_B, EK_A)
    dh1 = x25519_dh(our_signed_prekey_private, their_ephemeral_public)

    # DH2 = DH(SPK_B, IK_A_X25519)
    dh2 = x25519_dh(our_signed_prekey_private, their_x25519_identity_public)

    # DH3 = DH(IK_B_X25519, EK_A)
    our_x25519_identity = derive_x25519_from_ed25519(our_identity_private)
    dh3 = x25519_dh(our_x25519_identity, their_ephemeral_public)

    # DH4 = DH(OPK_B, EK_A) if OPK exists
    dh4 = b""
    if our_one_time_prekey_private is not None:
        dh4 = x25519_dh(our_one_time_prekey_private, their_ephemeral_public)

    # Concatenate DH outputs (same order as initiator)
    dh_combined = dh1 + dh2 + dh3 + dh4

    # Derive shared secret
    shared_secret = hkdf(
        salt=b"\x00" * 32,
        input_key_material=dh_combined,
        info=HKDF_INFO_X3DH,
        length=32,
    )

    # Associated data
    ad = (
        x25519_public_to_bytes(their_ephemeral_public) +
        x25519_public_to_bytes(our_signed_prekey_private.public_key()) +
        x25519_public_to_bytes(our_x25519_identity.public_key())
    )
    if our_one_time_prekey_private:
        ad += x25519_public_to_bytes(our_one_time_prekey_private.public_key())

    return X3DHOutput(
        shared_secret=shared_secret,
        associated_data=ad,
        used_one_time_prekey_id=our_one_time_prekey_id,
    )


# ==========================================================
# Key Bundle Parsing (from server response)
# ==========================================================

@dataclass
class ParsedKeyBundle:
    """Parsed key bundle from server."""
    device_id: str
    identity_key: ed25519.Ed25519PublicKey
    x25519_identity_key: x25519.X25519PublicKey
    signed_prekey: tuple[int, x25519.X25519PublicKey, bytes]  # (key_id, public_key, signature)
    one_time_prekeys: list[tuple[int, x25519.X25519PublicKey]]  # list of (key_id, public_key)


def parse_key_bundle(bundle_dict: dict) -> ParsedKeyBundle:
    """Parse a key bundle dictionary from server into usable key objects."""
    return ParsedKeyBundle(
        device_id=bundle_dict["device_id"],
        identity_key=ed25519_public_from_bytes(b64decode(bundle_dict["identity_key"])),
        x25519_identity_key=x25519_public_from_bytes(b64decode(bundle_dict["x25519_identity_key"])),
        signed_prekey=(
            bundle_dict["signed_prekey"]["key_id"],
            x25519_public_from_bytes(b64decode(bundle_dict["signed_prekey"]["public_key"])),
            b64decode(bundle_dict["signed_prekey"]["signature"]),
        ),
        one_time_prekeys=[
            (
                opk["key_id"],
                x25519_public_from_bytes(b64decode(opk["public_key"])),
            )
            for opk in bundle_dict.get("one_time_prekeys", [])
        ],
    )
