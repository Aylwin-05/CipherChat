from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class Decryption:

    @staticmethod
    def decrypt(
        ciphertext: bytes,
        nonce: bytes,
        key: bytes,
    ) -> str:

        aes = AESGCM(key)

        plaintext = aes.decrypt(
            nonce,
            ciphertext,
            None,
        )

        return plaintext.decode()
