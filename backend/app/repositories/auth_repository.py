from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import delete, select

from app.models.otp import OTPCode
from app.models.user import User
from app.repositories.base_repository import BaseRepository


class AuthRepository(BaseRepository):
    """
    Repository responsible for all authentication-related
    database operations.
    """

    def __init__(self, db):
        super().__init__(db)

    # ==========================================================
    # User Operations
    # ==========================================================

    async def get_user_by_email(
        self,
        email: str,
    ) -> User | None:
        result = await self.execute(
            select(User).where(User.email == email)
        )

        return result.scalar_one_or_none()

    async def get_user_by_id(
        self,
        user_id: UUID,
    ) -> User | None:
        result = await self.execute(
            select(User).where(User.id == user_id)
        )

        return result.scalar_one_or_none()

    async def create_user(
        self,
        user: User,
    ) -> User:
        return await self.create(user)

    # ==========================================================
    # OTP Operations
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
            .where(OTPCode.email == email)
            .where(OTPCode.is_used.is_(False))
            .order_by(OTPCode.created_at.desc())
        )

        return result.scalar_one_or_none()

    async def mark_otp_used(
        self,
        otp: OTPCode,
    ) -> None:
        otp.is_used = True
        await self.update()

    async def increment_attempts(
        self,
        otp: OTPCode,
    ) -> None:
        otp.attempts += 1
        await self.update()

    async def delete_existing_otps(
        self,
        email: str,
    ) -> int:
        """
        Delete all previous OTPs for an email.
        Only the newest OTP should remain valid.
        """

        result = await self.execute(
            delete(OTPCode).where(
                OTPCode.email == email
            )
        )

        await self.update()

        return result.rowcount or 0

    async def delete_expired_otps(self) -> int:
        """
        Delete all expired OTP records.
        """

        result = await self.execute(
            delete(OTPCode).where(
                OTPCode.expires_at < datetime.now(timezone.utc)
            )
        )

        await self.update()

        return result.rowcount or 0