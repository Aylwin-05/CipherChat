from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.repositories.user_key_repository import UserKeyRepository
from app.schemas.user_key import (
    PublicKeyResponse,
    RegisterKeysRequest,
)
from app.services.user_key_service import UserKeyService

router = APIRouter(
    prefix="/user-keys",
    tags=["User Keys"],
)


# ==========================================================
# Get User Public Key
# ==========================================================

@router.get(
    "/{user_id}",
    response_model=PublicKeyResponse,
)
async def get_public_key(
    user_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):

    repository = UserKeyRepository(db)

    service = UserKeyService(repository)

    key = await service.get_public_key(
        user_id
    )

    return PublicKeyResponse(
        user_id=str(key.user_id),
        public_key=key.public_key,
    )


# ==========================================================
# Register / Update Public Keys
# ==========================================================

@router.post(
    "/register",
)
async def register_keys(
    request: RegisterKeysRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):

    repository = UserKeyRepository(db)

    service = UserKeyService(repository)

    await service.register_keys(
        user=current_user,
        public_key=request.public_key,
        signed_prekey=request.signed_prekey,
        signed_prekey_signature=request.signed_prekey_signature,
    )

    return {
        "success": True,
        "message": "Public keys registered successfully.",
    }