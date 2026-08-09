from datetime import datetime, timedelta, timezone
from app.models.user_key import UserKey
from app.models.otp import OTPCode
from app.models.user import User
from app.repositories.auth_repository import AuthRepository
from app.services.email_service import EmailService
from app.utils.security import SecurityUtils


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

        if datetime.now(timezone.utc) > otp_record.expires_at:
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
    # =====================================================
    # REGISTER USER PUBLIC KEYS
    # =====================================================

    async def register_public_keys(
        self,
        user: User,
        public_key: str,
        signed_prekey: str,
        signed_prekey_signature: str,
    ):
        """
        Stores only the user's public cryptographic keys.

        Private keys NEVER reach the server.
        """

        existing = await self.repository.get_user_key(
            user.id
        )

        if existing:

            existing.public_key = public_key
            existing.signed_prekey = signed_prekey
            existing.signed_prekey_signature = (
                signed_prekey_signature
            )

            await self.repository.update_user_key(
                existing
            )

            await self.repository.commit()

            return existing

        key = UserKey(
            user_id=user.id,
            public_key=public_key,
            signed_prekey=signed_prekey,
            signed_prekey_signature=signed_prekey_signature,
        )

        await self.repository.create_user_key(
            key
        )

        await self.repository.commit()

        return key