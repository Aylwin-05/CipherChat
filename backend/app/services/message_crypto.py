import base64
import os

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class MessageCrypto:
    """
    CipherChat Hybrid Encryption Engine

    Hybrid Encryption
    -----------------
    RSA-2048
        ↓
    Encrypt AES-256 Key

    AES-256-GCM
        ↓
    Encrypt Message

    Backend stores only:
        ciphertext
        encrypted AES key
        nonce

    The backend never knows the plaintext.
    """

    AES_KEY_SIZE = 32
    NONCE_SIZE = 12

    # ==========================================================
    # Base64 Helpers
    # ==========================================================

    @staticmethod
    def b64_encode(data: bytes) -> str:
        return base64.b64encode(data).decode("utf-8")

    @staticmethod
    def b64_decode(value: str) -> bytes:
        return base64.b64decode(value.encode("utf-8"))

    # ==========================================================
    # AES Key
    # ==========================================================

    @staticmethod
    def generate_aes_key() -> bytes:
        return os.urandom(MessageCrypto.AES_KEY_SIZE)

    # ==========================================================
    # RSA Loading
    # ==========================================================

    @staticmethod
    def load_public_key(public_key: bytes):

        return serialization.load_pem_public_key(
            public_key
        )

    @staticmethod
    def load_private_key(private_key: bytes):

        return serialization.load_pem_private_key(
            private_key,
            password=None,
        )

    # ==========================================================
    # RSA Encrypt AES Key
    # ==========================================================

    @classmethod
    def encrypt_aes_key(
        cls,
        aes_key: bytes,
        receiver_public_key: bytes,
    ) -> bytes:

        public_key = cls.load_public_key(
            receiver_public_key
        )

        return public_key.encrypt(
            aes_key,
            padding.OAEP(
                mgf=padding.MGF1(
                    algorithm=hashes.SHA256(),
                ),
                algorithm=hashes.SHA256(),
                label=None,
            ),
        )

    # ==========================================================
    # RSA Decrypt AES Key
    # ==========================================================

    @classmethod
    def decrypt_aes_key(
        cls,
        encrypted_key: bytes,
        receiver_private_key: bytes,
    ) -> bytes:

        private_key = cls.load_private_key(
            receiver_private_key
        )

        return private_key.decrypt(
            encrypted_key,
            padding.OAEP(
                mgf=padding.MGF1(
                    algorithm=hashes.SHA256(),
                ),
                algorithm=hashes.SHA256(),
                label=None,
            ),
        )

    # ==========================================================
    # AES Encrypt
    # ==========================================================

    @classmethod
    def encrypt_message(
        cls,
        plaintext: str,
        aes_key: bytes,
    ) -> tuple[bytes, bytes]:

        nonce = os.urandom(
            cls.NONCE_SIZE
        )

        aes = AESGCM(
            aes_key
        )

        ciphertext = aes.encrypt(
            nonce,
            plaintext.encode(),
            None,
        )

        return ciphertext, nonce

    # ==========================================================
    # AES Decrypt
    # ==========================================================

    @classmethod
    def decrypt_message(
        cls,
        ciphertext: bytes,
        nonce: bytes,
        aes_key: bytes,
    ) -> str:

        aes = AESGCM(
            aes_key
        )

        plaintext = aes.decrypt(
            nonce,
            ciphertext,
            None,
        )

        return plaintext.decode()

    # ==========================================================
    # Hybrid Encrypt
    # ==========================================================

    @classmethod
    def encrypt_for_receiver(
        cls,
        plaintext: str,
        receiver_public_key: bytes,
    ) -> dict:

        aes_key = cls.generate_aes_key()

        ciphertext, nonce = cls.encrypt_message(
            plaintext,
            aes_key,
        )

        encrypted_key = cls.encrypt_aes_key(
            aes_key,
            receiver_public_key,
        )

        return {
            "ciphertext": cls.b64_encode(
                ciphertext
            ),
            "encrypted_key": cls.b64_encode(
                encrypted_key
            ),
            "nonce": cls.b64_encode(
                nonce
            ),
        }

    # ==========================================================
    # Hybrid Decrypt
    # ==========================================================

    @classmethod
    def decrypt_from_sender(
        cls,
        ciphertext: str,
        encrypted_key: str,
        nonce: str,
        receiver_private_key: bytes,
    ) -> str:

        aes_key = cls.decrypt_aes_key(
            cls.b64_decode(encrypted_key),
            receiver_private_key,
        )

        return cls.decrypt_message(
            cls.b64_decode(ciphertext),
            cls.b64_decode(nonce),
            aes_key,
        )