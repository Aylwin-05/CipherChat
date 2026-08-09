from uuid import UUID

from fastapi import HTTPException

from app.models.user import User
from app.models.user_key import UserKey
from app.repositories.user_key_repository import UserKeyRepository


class UserKeyService:
    """
    Handles user public key operations.

    The backend NEVER generates keys.
    The backend NEVER stores plaintext private keys.
    The backend ONLY stores public cryptographic material.
    """

    def __init__(
        self,
        repository: UserKeyRepository,
    ):
        self.repository = repository

    # ==========================================================
    # Register / Update Keys
    # ==========================================================

    async def register_keys(
        self,
        user: User,
        public_key: str,
        signed_prekey: str,
        signed_prekey_signature: str,
    ):

        key = await self.repository.get_by_user_id(
            user.id
        )

        if key is None:

            key = UserKey(
                user_id=user.id,
                public_key=public_key,
                signed_prekey=signed_prekey,
                signed_prekey_signature=signed_prekey_signature,
            )

            await self.repository.create_key(key)

        else:

            key.public_key = public_key
            key.signed_prekey = signed_prekey
            key.signed_prekey_signature = (
                signed_prekey_signature
            )

            await self.repository.save(key)

        return key

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

        return key