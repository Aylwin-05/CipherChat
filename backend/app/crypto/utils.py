import base64
import secrets


def random_bytes(length: int) -> bytes:
    """
    Generate cryptographically secure random bytes.
    """
    return secrets.token_bytes(length)


def b64encode(data: bytes) -> str:
    """
    Convert bytes to Base64 string.
    """
    return base64.b64encode(data).decode("utf-8")


def b64decode(data: str) -> bytes:
    """
    Convert Base64 string back to bytes.
    """
    return base64.b64decode(data.encode("utf-8"))
