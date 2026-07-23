import base64
import os

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF


class CryptoService:
    """
    CipherChat Cryptography Service

    Responsibilities
    ----------------
    ✔ Generate X25519 identity keys
    ✔ Encrypt private keys
    ✔ Decrypt private keys
    ✔ Derive shared secrets
    ✔ Encrypt messages
    ✔ Decrypt messages

    Future
    ------
    ✔ Signed PreKeys
    ✔ One-Time PreKeys
    ✔ Double Ratchet
    """

    def __init__(self):
        pass

    # ==========================================================
    # Identity Key Pair
    # ==========================================================

    def generate_identity_keypair(self):

        private_key = x25519.X25519PrivateKey.generate()

        public_key = private_key.public_key()

        return private_key, public_key

    # ==========================================================
    # Serialize Keys
    # ==========================================================

    def serialize_public_key(
        self,
        public_key,
    ) -> bytes:

        return public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )

    def serialize_private_key(
        self,
        private_key,
    ) -> bytes:

        return private_key.private_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PrivateFormat.Raw,
            encryption_algorithm=serialization.NoEncryption(),
        )

    # ==========================================================
    # Load Keys
    # ==========================================================

    def load_public_key(
        self,
        data: bytes,
    ):

        return x25519.X25519PublicKey.from_public_bytes(
            data
        )

    def load_private_key(
        self,
        data: bytes,
    ):

        return x25519.X25519PrivateKey.from_private_bytes(
            data
        )

    # ==========================================================
    # Shared Secret
    # ==========================================================

    def derive_shared_secret(
        self,
        private_key,
        peer_public_key,
    ) -> bytes:

        return private_key.exchange(
            peer_public_key
        )

    # ==========================================================
    # HKDF
    # ==========================================================

    def derive_aes_key(
        self,
        shared_secret: bytes,
    ) -> bytes:

        hkdf = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=None,
            info=b"CipherChat",
        )

        return hkdf.derive(shared_secret)

    # ==========================================================
    # AES-256-GCM
    # ==========================================================

    def encrypt_message(
        self,
        key: bytes,
        plaintext: str,
    ):

        nonce = os.urandom(12)

        aes = AESGCM(key)

        ciphertext = aes.encrypt(
            nonce,
            plaintext.encode(),
            None,
        )

        return (
            base64.b64encode(
                nonce
            ).decode(),

            base64.b64encode(
                ciphertext
            ).decode(),
        )

    def decrypt_message(
        self,
        key: bytes,
        nonce: str,
        ciphertext: str,
    ) -> str:

        aes = AESGCM(key)

        plaintext = aes.decrypt(
            base64.b64decode(nonce),
            base64.b64decode(ciphertext),
            None,
        )

        return plaintext.decode()