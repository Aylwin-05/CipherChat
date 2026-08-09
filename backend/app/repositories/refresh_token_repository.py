import hashlib
import uuid
from datetime import datetime, timezone

from sqlalchemy import delete, select, update

from app.models.refresh_token import RefreshToken


class RefreshTokenRepository:
    """
    Persistence for refresh tokens (rotation + revocation).
    """

    def __init__(self, db):
        self.db = db

    @staticmethod
    def hash_token(token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()

    async def get_by_token_hash(
        self,
        token_hash: str,
    ) -> RefreshToken | None:
        result = await self.db.execute(
            select(RefreshToken).where(
                RefreshToken.token_hash == token_hash
            )
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        record: RefreshToken,
    ) -> RefreshToken:
        self.db.add(record)
        await self.db.flush()
        return record

    async def revoke(
        self,
        record: RefreshToken,
        replaced_by_jti: str | None = None,
    ):
        record.revoked_at = datetime.now(timezone.utc)
        if replaced_by_jti:
            record.replaced_by_jti = replaced_by_jti
        await self.db.flush()

    async def revoke_family(
        self,
        family_id: uuid.UUID,
    ):
        await self.db.execute(
            update(RefreshToken)
            .where(RefreshToken.family_id == family_id)
            .values(revoked_at=datetime.now(timezone.utc))
            .execution_options(synchronize_session=False)
        )
        await self.db.flush()

    async def revoke_all_for_user(
        self,
        user_id: uuid.UUID,
    ):
        await self.db.execute(
            update(RefreshToken)
            .where(
                RefreshToken.user_id == user_id,
                RefreshToken.revoked_at.is_(None),
            )
            .values(revoked_at=datetime.now(timezone.utc))
            .execution_options(synchronize_session=False)
        )
        await self.db.flush()

    async def delete_expired(self):
        await self.db.execute(
            delete(RefreshToken).where(
                RefreshToken.expires_at
                < datetime.now(timezone.utc)
            )
        )
        await self.db.flush()

    async def commit(self):
        await self.db.commit()


class RefreshTokenError(Exception):
    def __init__(self, message: str, code: str = "invalid_token"):
        super().__init__(message)
        self.code = code