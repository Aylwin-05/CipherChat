from datetime import datetime, timedelta, timezone

from app.models.otp import OTPCode
from app.models.user import User
from app.models.user_key import UserKey
from app.repositories.auth_repository import AuthRepository
from app.services.email_service import EmailService
from app.services.encryption_service import EncryptionService
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

        # Commit OTP so it exists before sending email
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

        print("\n========== VERIFY OTP ==========")
        print("Email:", email)
        print("OTP Entered:", otp)

        otp_record = await self.repository.get_latest_otp(
            email
        )

        print("OTP Record:", otp_record)

        if otp_record is None:
            print("FAILED -> No OTP record found")
            return None

        if otp_record.is_used:
            print("FAILED -> OTP already used")
            return None

        if otp_record.attempts >= self.MAX_ATTEMPTS:
            print("FAILED -> Maximum attempts exceeded")
            return None

        if (
            datetime.now(timezone.utc)
            > otp_record.expires_at
        ):
            print("FAILED -> OTP expired")
            return None

        if not SecurityUtils.verify_otp(
            otp,
            otp_record.otp_hash,
        ):
            print("FAILED -> Incorrect OTP")

            await self.repository.increment_attempts(
                otp_record
            )

            await self.repository.commit()

            return None

        print("SUCCESS -> OTP Verified")

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

            print("Existing user login")

            return {
                "user": existing_user,
                "private_key": None,
            }

        # =====================================================
        # New User Registration
        # =====================================================

        print("Creating new user...")

        username = email.split("@")[0]

        keys = (
            EncryptionService.generate_key_pair()
        )

        user = User(
            email=email,
            username=username,
            display_name=username,
            is_verified=True,
        )

        try:

            await self.repository.create_user(user)

            user_key = UserKey(
                user_id=user.id,
                public_key=keys["public_key"],
                private_key_encrypted=keys[
                    "encrypted_private_key"
                ],
            )

            await self.repository.create_user_key(
                user_key
            )

            await self.repository.commit()

            await self.repository.refresh_all(
                user,
                user_key,
            )

            print("New user created successfully")

        except Exception as e:

            await self.repository.rollback()

            print("Registration failed:", e)

            raise

        return {
            "user": user,
            "private_key": EncryptionService.export_private_key_base64(
                keys["private_key"]
            ),
        }