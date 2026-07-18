from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt

from app.core.config import settings


class JWTService:
    """
    Handles JWT creation and verification.
    """

    def __init__(self):
        self.secret_key = settings.SECRET_KEY
        self.algorithm = settings.JWT_ALGORITHM
        self.access_token_expire = (
            settings.ACCESS_TOKEN_EXPIRE_MINUTES
        )
        self.refresh_token_expire = (
            settings.REFRESH_TOKEN_EXPIRE_DAYS
        )

    # ======================================================
    # Access Token
    # ======================================================

    def create_access_token(
        self,
        user_id: str,
        email: str,
    ) -> str:

        expire = datetime.now(timezone.utc) + timedelta(
            minutes=self.access_token_expire
        )

        payload = {
            "sub": user_id,
            "email": email,
            "type": "access",
            "exp": expire,
        }

        return jwt.encode(
            payload,
            self.secret_key,
            algorithm=self.algorithm,
        )

    # ======================================================
    # Refresh Token
    # ======================================================

    def create_refresh_token(
        self,
        user_id: str,
        email: str,
    ) -> str:

        expire = datetime.now(timezone.utc) + timedelta(
            days=self.refresh_token_expire
        )

        payload = {
            "sub": user_id,
            "email": email,
            "type": "refresh",
            "exp": expire,
        }

        return jwt.encode(
            payload,
            self.secret_key,
            algorithm=self.algorithm,
        )

    # ======================================================
    # Decode
    # ======================================================

    def decode_token(
        self,
        token: str,
    ) -> dict[str, Any] | None:

        try:
            payload = jwt.decode(
                token,
                self.secret_key,
                algorithms=[self.algorithm],
            )

            return payload

        except JWTError:
            return None

    # ======================================================
    # Validation
    # ======================================================

    def verify_access_token(
        self,
        token: str,
    ) -> dict[str, Any] | None:

        payload = self.decode_token(token)

        if payload is None:
            return None

        if payload.get("type") != "access":
            return None

        return payload

    def verify_refresh_token(
        self,
        token: str,
    ) -> dict[str, Any] | None:

        payload = self.decode_token(token)

        if payload is None:
            return None

        if payload.get("type") != "refresh":
            return None

        return payload