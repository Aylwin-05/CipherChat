from datetime import datetime, timedelta, timezone

from app.models.otp import OTPCode
from app.models.user import User
from app.repositories.auth_repository import AuthRepository
from app.services.email_service import EmailService
from app.utils.security import SecurityUtils


class AuthService:
    """
    Handles authentication business logic.
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
    ) -> bool:
        """
        Generate, store and send OTP.
        """

        # Remove expired OTPs
        await self.repository.delete_expired_otps()

        # Remove previous OTPs for this email
        await self.repository.delete_existing_otps(email)

        # Generate OTP
        otp = SecurityUtils.generate_otp()

        # Hash OTP
        otp_hash = SecurityUtils.hash_otp(otp)

        otp_record = OTPCode(
            email=email,
            otp_hash=otp_hash,
            expires_at=datetime.now(timezone.utc)
            + timedelta(minutes=self.OTP_EXPIRY_MINUTES),
        )

        await self.repository.create_otp(otp_record)

        # Send Email
        self.email_service.send_otp_email(
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
    ) -> User | None:
        """
        Verify OTP and return authenticated user.
        """

        otp_record = await self.repository.get_latest_otp(email)

        if otp_record is None:
            return None

        if otp_record.is_used:
            return None

        if otp_record.attempts >= self.MAX_ATTEMPTS:
            return None

        if datetime.now(timezone.utc) > otp_record.expires_at:
            return None

        if not SecurityUtils.verify_otp(
            otp,
            otp_record.otp_hash,
        ):
            await self.repository.increment_attempts(
                otp_record
            )
            return None

        await self.repository.mark_otp_used(
            otp_record
        )

        user = await self.repository.get_user_by_email(
            email
        )

        if user:
            return user

        username = email.split("@")[0]

        new_user = User(
            email=email,
            username=username,
            display_name=username,
            is_verified=True,
        )

        return await self.repository.create_user(
            new_user
        )