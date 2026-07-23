from cryptography.hazmat.primitives.asymmetric.x25519 import (
    X25519PrivateKey,
    X25519PublicKey,
)
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    PublicFormat,
)


class KeyManager:
    """
    Responsible for generating long-term identity keys.
    """

    @staticmethod
    def generate_keypair():

        private_key = X25519PrivateKey.generate()

        public_key = private_key.public_key()

        return private_key, public_key

    @staticmethod
    def serialize_public_key(public_key: X25519PublicKey) -> bytes:

        return public_key.public_bytes(
            encoding=Encoding.Raw,
            format=PublicFormat.Raw,
        )

    @staticmethod
    def deserialize_public_key(data: bytes):

        return X25519PublicKey.from_public_bytes(data)