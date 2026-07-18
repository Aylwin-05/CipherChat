import hashlib
import secrets
from hmac import compare_digest


class SecurityUtils:
    """
    Cryptographic helper functions used throughout CipherChat.
    """

    OTP_LENGTH = 6

    @staticmethod
    def generate_otp() -> str:
        """
        Generate a cryptographically secure 6-digit OTP.
        """
        return f"{secrets.randbelow(10**6):06d}"

    @staticmethod
    def hash_otp(otp: str) -> str:
        """
        Return SHA-256 hash of an OTP.
        """
        return hashlib.sha256(otp.encode("utf-8")).hexdigest()

    @staticmethod
    def verify_otp(plain_otp: str, hashed_otp: str) -> bool:
        """
        Constant-time OTP comparison.
        """
        return compare_digest(
            SecurityUtils.hash_otp(plain_otp),
            hashed_otp,
        )