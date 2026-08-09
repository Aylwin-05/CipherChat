"""
Token family management: issue, rotate and revoke refresh tokens.

Every refresh token carries a unique `jti` and is recorded
(hashed) server-side. Using one rotates it (old -> new, same
family). Reusing a rotated/revoked token is detected and the
entire family is revoked — this contains stolen tokens the
moment they get replayed.
"""

import uuid
from datetime import datetime, timedelta, timezone

from app.core.config import settings
from app.models.refresh_token import RefreshToken
from app.repositories.refresh_token_repository import (
    RefreshTokenError,
    RefreshTokenRepository,
)
from app.services.jwt_service import JWTService


class RefreshTokenService:
    def __init__(self, repository: RefreshTokenRepository):
        self.repository = repository
        self.jwt = JWTService()

    # ======================================================
    # Issue
    # ======================================================

    async def issue(
        self,
        user_id,
        *,
        family_id: uuid.UUID | None = None,
        user_agent: str | None = None,
        ip_address: str | None = None,
    ) -> str:
        """Create a new refresh token and record it server-side."""

        jti = uuid.uuid4().hex
        token = self.jwt.create_refresh_token(
            user_id=str(user_id),
            email="",
            jti=jti,
        )

        record = RefreshToken(
            user_id=user_id,
            jti=jti,
            token_hash=RefreshTokenRepository.hash_token(token),
            family_id=family_id or uuid.uuid4(),
            expires_at=datetime.now(timezone.utc)
            + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
            user_agent=user_agent,
            ip_address=ip_address,
        )
        await self.repository.create(record)
        await self.repository.commit()
        return token

    # ======================================================
    # Rotate (used by /auth/refresh)
    # ======================================================

    async def rotate(
        self,
        token: str,
        *,
        user_agent: str | None = None,
        ip_address: str | None = None,
    ) -> tuple[str, bool]:
        """
        Validate a refresh token and replace it with a new one.

        Returns (new_token, new_access_token).
        Raises RefreshTokenError when the token is unknown,
        expired or already rotated (reuse detected).
        """

        payload = self.jwt.verify_refresh_token(token)

        if payload is None:
            raise RefreshTokenError("Invalid refresh token.")

        token_hash = RefreshTokenRepository.hash_token(token)
        record = await self.repository.get_by_token_hash(token_hash)

        if record is None:
            # A valid JWT we never issued (e.g. replayed after
            # rotation): revoke the family it claims to belong to.
            jti = payload.get("jti")
            if jti:
                await self.repository.revoke_family(uuid.UUID(jti))
            raise RefreshTokenError("Refresh token reuse detected.")

        if record.revoked_at is not None:
            await self.repository.revoke_family(record.family_id)
            await self.repository.commit()
            raise RefreshTokenError("Refresh token reuse detected.")

        expires = record.expires_at

        if expires.tzinfo is None:

            expires = expires.replace(tzinfo=timezone.utc)

        if datetime.now(timezone.utc) > expires:
            await self.repository.revoke(record)
            await self.repository.commit()
            raise RefreshTokenError("Refresh token expired.")

        if str(record.user_id) != payload.get("sub"):
            raise RefreshTokenError("Refresh token mismatch.")

        # -- rotate -------------------------------------------------
        new_jti = uuid.uuid4().hex
        new_token = self.jwt.create_refresh_token(
            user_id=str(record.user_id),
            email=payload.get("email", ""),
            jti=new_jti,
        )

        await self.repository.revoke(
            record,
            replaced_by_jti=new_jti,
        )

        await self.repository.create(
            RefreshToken(
                user_id=record.user_id,
                jti=new_jti,
                token_hash=RefreshTokenRepository.hash_token(new_token),
                family_id=record.family_id,
                expires_at=datetime.now(timezone.utc)
                + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
                user_agent=user_agent,
                ip_address=ip_address,
            )
        )

        await self.repository.commit()

        return new_token

    # ======================================================
    # Revoke
    # ======================================================

    async def revoke_token(
        self,
        token: str,
    ) -> bool:
        """Revoke a single refresh token (logout of one device)."""

        token_hash = RefreshTokenRepository.hash_token(token)
        record = await self.repository.get_by_token_hash(token_hash)

        if record is None or record.revoked_at is not None:
            await self.repository.commit()
            return False

        await self.repository.revoke(record)
        await self.repository.commit()
        return True

    async def revoke_family(
        self,
        token: str,
    ) -> bool:
        """Revoke every token sharing the session family."""

        token_hash = RefreshTokenRepository.hash_token(token)
        record = await self.repository.get_by_token_hash(token_hash)

        if record is None:
            await self.repository.commit()
            return False

        await self.repository.revoke_family(record.family_id)
        await self.repository.commit()
        return True
