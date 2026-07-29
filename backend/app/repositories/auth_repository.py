from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import delete, select

from app.models.otp import OTPCode
from app.models.user import User
from app.models.user_key import UserKey
from app.repositories.base_repository import BaseRepository


class AuthRepository(BaseRepository):
    """
    Repository responsible for authentication,
    OTPs and cryptographic identity keys.
    """

    # ==========================================================
    # Users
    # ==========================================================

    async def get_user_by_email(
        self,
        email: str,
    ) -> User | None:

        result = await self.execute(
            select(User).where(
                User.email == email
            )
        )

        return result.scalar_one_or_none()

    async def get_user_by_username(
        self,
        username: str,
    ) -> User | None:

        result = await self.execute(
            select(User).where(
                User.username == username
            )
        )

        return result.scalar_one_or_none()

    async def get_user_by_id(
        self,
        user_id,
    ) -> User | None:

        result = await self.execute(
            select(User).where(
                User.id == user_id
            )
        )

        return result.scalar_one_or_none()

    async def update_user_key(
        self,
        key: UserKey,
    ) -> UserKey:

        await self.update()

        return key

    async def create_user(
        self,
        user: User,
    ) -> User:

        self.db.add(user)

        await self.db.flush()

        return user

    # ==========================================================
    # User Keys
    # ==========================================================

    async def create_user_key(
        self,
        key: UserKey,
    ) -> UserKey:

        self.db.add(key)

        await self.db.flush()

        return key

    async def get_user_key(
        self,
        user_id: UUID,
    ) -> UserKey | None:

        result = await self.execute(
            select(UserKey).where(
                UserKey.user_id == user_id
            )
        )

        return result.scalar_one_or_none()

    # ==========================================================
    # OTP
    # ==========================================================

    async def create_otp(
        self,
        otp: OTPCode,
    ) -> OTPCode:

        return await self.create(otp)

    async def get_latest_otp(
        self,
        email: str,
    ) -> OTPCode | None:

        result = await self.execute(
            select(OTPCode)
            .where(
                OTPCode.email == email
            )
            .where(
                OTPCode.is_used.is_(False)
            )
            .order_by(
                OTPCode.created_at.desc()
            )
        )

        return result.scalar_one_or_none()

    async def mark_otp_used(
        self,
        otp: OTPCode,
    ):

        otp.is_used = True

        await self.update()

    async def increment_attempts(
        self,
        otp: OTPCode,
    ):

        otp.attempts += 1

        await self.update()

    async def delete_existing_otps(
        self,
        email: str,
    ):

        await self.execute(
            delete(OTPCode).where(
                OTPCode.email == email
            )
        )

        await self.update()

    async def delete_expired_otps(
        self,
    ):

        await self.execute(
            delete(OTPCode).where(
                OTPCode.expires_at
                < datetime.now(timezone.utc)
            )
        )

        await self.update()

    # ==========================================================
    # Transaction Helpers
    # ==========================================================

    async def commit(self):

        await self.db.commit()

    async def rollback(self):

        await self.db.rollback()

    async def refresh_all(
        self,
        user: User,
        key: UserKey,
    ):

        await self.db.refresh(user)

        await self.db.refresh(key)