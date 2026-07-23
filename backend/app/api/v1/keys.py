from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db
from app.dependencies.auth import get_current_user

from app.models.user import User

from app.repositories.auth_repository import AuthRepository

from app.schemas.keys import (
    UploadPublicKeyRequest,
    PublicKeyResponse,
)

from app.services.key_service import KeyService

router = APIRouter(
    prefix="/keys",
    tags=["Encryption Keys"],
)


# ==========================================================
# Upload Public Key
# ==========================================================

@router.post("/public")
async def upload_public_key(
    request: UploadPublicKeyRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):

    repository = AuthRepository(db)

    service = KeyService(repository)

    return await service.upload_public_key(
        current_user,
        request.public_key,
    )


# ==========================================================
# Get Public Key
# ==========================================================

@router.get(
    "/{user_id}",
    response_model=PublicKeyResponse,
)
async def get_public_key(
    user_id,
    db: AsyncSession = Depends(get_db),
):

    repository = AuthRepository(db)

    service = KeyService(repository)

    return await service.get_public_key(
        user_id,
    )