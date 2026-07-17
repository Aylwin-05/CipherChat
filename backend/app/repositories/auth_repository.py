from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.otp import OTPCode
from app.models.user import User


class AuthRepository:
    """
    Handles authentication-related database operations.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    # ------------------------
    # User Queries
    # ------------------------

    async def get_user_by_email(self, email: str) -> User | None:
        result = await self.db.execute(
            select(User).where(User.email == email)
        )
        return result.scalar_one_or_none()

    async def create_user(self, user: User) -> User:
        self.db.add(user)
        await self.db.commit()
        await self.db.refresh(user)
        return user

    # ------------------------
    # OTP Queries
    # ------------------------

    async def create_otp(self, otp: OTPCode) -> OTPCode:
        self.db.add(otp)
        await self.db.commit()
        await self.db.refresh(otp)
        return otp

    async def get_latest_otp(self, email: str) -> OTPCode | None:
        result = await self.db.execute(
            select(OTPCode)
            .where(OTPCode.email == email)
            .order_by(OTPCode.created_at.desc())
        )

        return result.scalar_one_or_none()

    async def update(self):
        await self.db.commit()