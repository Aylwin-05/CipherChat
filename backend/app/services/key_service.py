from uuid import UUID

from fastapi import HTTPException

from app.models.user import User
from app.repositories.auth_repository import AuthRepository


class KeyService:
    """
    Handles public encryption keys.
    """

    def __init__(
        self,
        repository: AuthRepository,
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

        current_user.public_key = public_key

        await self.repository.save()

        return {
            "message": "Public key uploaded successfully."
        }

    # ==========================================================
    # Get Public Key
    # ==========================================================

    async def get_public_key(
        self,
        user_id: UUID,
    ):

        user = await self.repository.get_user_by_id(
            user_id
        )

        if not user:
            raise HTTPException(
                status_code=404,
                detail="User not found.",
            )

        return {
            "user_id": user.id,
            "public_key": user.public_key,
        }