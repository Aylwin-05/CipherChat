import base64

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.core.config import settings


class EncryptionService:
    """
    Nexara Encryption Service

    Responsibilities
    ----------------
    ✔ Generate RSA key pairs
    ✔ Serialize keys
    ✔ Encrypt private keys
    ✔ Decrypt private keys

    Future
    -------
    ✔ Hybrid Encryption (RSA + AES)
    ✔ Message Encryption
    ✔ Attachment Encryption
    """

    # ==========================================================
    # Master Key
    # ==========================================================

    @staticmethod
    def get_master_key() -> bytes:
        """
        Returns the server master key from the
        application settings.
        """

        if not settings.MASTER_KEY:

            raise RuntimeError(
                "MASTER_KEY is missing from configuration."
            )

        return settings.MASTER_KEY.encode()

    # ==========================================================
    # Fernet
    # ==========================================================

    @classmethod
    def get_fernet(cls):

        return Fernet(
            cls.get_master_key()
        )

    # ==========================================================
    # Generate RSA Key Pair
    # ==========================================================

    @classmethod
    def generate_key_pair(cls):

        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
        )

        public_key = private_key.public_key()

        private_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )

        public_pem = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )

        encrypted_private_key = cls.encrypt_private_key(
            private_pem
        )

        return {
            "public_key": public_pem,
            "private_key": private_pem,
            "encrypted_private_key": encrypted_private_key,
        }

    # ==========================================================
    # Encrypt Private Key
    # ==========================================================

    @classmethod
    def encrypt_private_key(
        cls,
        private_key: bytes,
    ) -> bytes:

        return cls.get_fernet().encrypt(
            private_key
        )

    # ==========================================================
    # Decrypt Private Key
    # ==========================================================

    @classmethod
    def decrypt_private_key(
        cls,
        encrypted_private_key: bytes,
    ) -> bytes:

        return cls.get_fernet().decrypt(
            encrypted_private_key
        )

    # ==========================================================
    # Export Public Key
    # ==========================================================

    @staticmethod
    def export_public_key_base64(
        public_key: bytes,
    ) -> str:

        return base64.b64encode(
            public_key
        ).decode()

    # ==========================================================
    # Export Private Key
    # ==========================================================

    @staticmethod
    def export_private_key_base64(
        private_key: bytes,
    ) -> str:

        return base64.b64encode(
            private_key
        ).decode()

    # ==========================================================
    # Import Public Key
    # ==========================================================

    @staticmethod
    def import_public_key_base64(
        value: str,
    ) -> bytes:

        return base64.b64decode(
            value
        )

    # ==========================================================
    # Import Private Key
    # ==========================================================

    @staticmethod
    def import_private_key_base64(
        value: str,
    ) -> bytes:

        return base64.b64decode(
            value
        )