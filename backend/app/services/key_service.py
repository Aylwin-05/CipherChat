from base64 import b64decode, b64encode
from uuid import UUID

from fastapi import HTTPException

from app.models.user import User
from app.models.user_key import UserKey
from app.repositories.user_key_repository import UserKeyRepository


class KeyService:
    """
    Handles public key management.

    Backend stores ONLY the public key.

    Private keys never leave the client.
    """

    def __init__(
        self,
        repository: UserKeyRepository,
    ):
        self.repository = repository

    # ==========================================================
    # Upload Public Key
    # ==========================================================

    async def upload_public_key(
        self,
        current_user: User,
        public_key: str,
    ):

        existing = await self.repository.get_by_user_id(
            current_user.id
        )

        public_key_bytes = b64decode(public_key)

        if existing:

            existing.public_key = public_key_bytes

            await self.repository.save(existing)

            return {
                "success": True,
                "message": "Public key updated.",
            }

        key = UserKey(
            user_id=current_user.id,
            public_key=public_key_bytes,

            # kept only because your DB schema currently requires it
            private_key_encrypted=b"",
        )

        await self.repository.create_key(key)

        return {
            "success": True,
            "message": "Public key uploaded.",
        }

    # ==========================================================
    # Get Public Key
    # ==========================================================

    async def get_public_key(
        self,
        user_id: UUID,
    ):

        key = await self.repository.get_by_user_id(
            user_id
        )

        if key is None:

            raise HTTPException(
                status_code=404,
                detail="Public key not found.",
            )

        return {
            "public_key": b64encode(
                key.public_key
            ).decode()
        }