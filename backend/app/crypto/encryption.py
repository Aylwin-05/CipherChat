from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.crypto.utils import (
    random_bytes,
)


class Encryption:

    @staticmethod
    def encrypt(
        plaintext: str,
        key: bytes,
    ):

        nonce = random_bytes(12)

        aes = AESGCM(key)

        ciphertext = aes.encrypt(
            nonce,
            plaintext.encode(),
            None,
        )

        return {
            "ciphertext": ciphertext,
            "nonce": nonce,
        }