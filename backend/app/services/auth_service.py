import logging

from datetime import datetime, timedelta, timezone

from app.core.config import settings
from app.models.otp import OTPCode
from app.models.user import User
from app.repositories.auth_repository import AuthRepository
from app.services.email_service import EmailService
from app.utils.security import SecurityUtils

logger = logging.getLogger(__name__)


class AuthService:
    """
    Handles authentication business logic.

    In the E2EE architecture:

    • Backend NEVER generates encryption keys.
    • Backend NEVER stores private keys.
    • Backend only authenticates users.
    """

    OTP_EXPIRY_MINUTES = 5
    MAX_ATTEMPTS = 5

    def __init__(
        self,
        repository: AuthRepository,
    ):
        self.repository = repository
        self.email_service = EmailService()

    # =====================================================
    # SEND OTP
    # =====================================================

    async def send_otp(
        self,
        email: str,
        client_ip: str | None = None,
    ) -> bool:

        await self.repository.delete_expired_otps()
        await self.repository.delete_existing_otps(email)

        otp = SecurityUtils.generate_otp()

        otp_hash = SecurityUtils.hash_otp(otp)

        otp_record = OTPCode(
            email=email,
            otp_hash=otp_hash,
            expires_at=datetime.now(timezone.utc)
            + timedelta(minutes=self.OTP_EXPIRY_MINUTES),
        )

        await self.repository.create_otp(otp_record)

        await self.repository.commit()

        # ==================================================
        # DEVELOPMENT shortcut: print the OTP to the server
        # console instead of sending real mail (DEBUG only)
        # ==================================================

        if settings.DEBUG and settings.APP_ENV == "development":

            logger.warning(
                "[DEV] OTP for %s: %s",
                email,
                otp,
            )

        await self.email_service.send_otp_email(
            recipient_email=email,
            otp=otp,
        )

        return True

    # =====================================================
    # VERIFY OTP
    # =====================================================

    async def verify_otp(
        self,
        email: str,
        otp: str,
    ):

        otp_record = await self.repository.get_latest_otp(
            email
        )

        if otp_record is None:
            return None

        if otp_record.is_used:
            return None

        if otp_record.attempts >= self.MAX_ATTEMPTS:
            return None

        expires_at = otp_record.expires_at

        if expires_at.tzinfo is None:

            expires_at = expires_at.replace(
                tzinfo=timezone.utc
            )

        if datetime.now(timezone.utc) > expires_at:
            return None

        if not SecurityUtils.verify_otp(
            otp,
            otp_record.otp_hash,
        ):

            await self.repository.increment_attempts(
                otp_record
            )

            await self.repository.commit()

            return None

        await self.repository.mark_otp_used(
            otp_record
        )

        # =====================================================
        # Existing User
        # =====================================================

        existing_user = (
            await self.repository.get_user_by_email(
                email
            )
        )

        if existing_user:

            await self.repository.commit()

            return {
                "user": existing_user,
            }

        # =====================================================
        # New User Registration
        # =====================================================

        base_username = (
            email.split("@")[0]
            .strip()
            .lower()
        )

        username = base_username

        counter = 1

        # Generate a unique username
        while await self.repository.get_user_by_username(
            username
        ):

            username = f"{base_username}{counter}"

            counter += 1

        user = User(
            email=email,
            username=username,
            display_name=username,
            is_verified=True,
        )

        try:

            await self.repository.create_user(
                user
            )

            await self.repository.commit()

            await self.repository.refresh(
                user
            )

        except Exception:

            await self.repository.rollback()

            raise

        return {
            "user": user,
        }