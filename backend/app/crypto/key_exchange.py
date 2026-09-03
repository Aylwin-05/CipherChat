from cryptography.hazmat.primitives.asymmetric.x25519 import (
    X25519PrivateKey,
    X25519PublicKey,
)


class KeyExchange:
    """
    Performs X25519 Diffie-Hellman key exchange.
    """

    @staticmethod
    def derive_shared_secret(
        private_key: X25519PrivateKey,
        public_key: X25519PublicKey,
    ) -> bytes:

        return private_key.exchange(public_key)
