from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db
from app.dependencies.auth import get_current_user

from app.models.user import User

from app.repositories.user_key_repository import (
    UserKeyRepository,
)

from app.schemas.keys import (
    UploadPublicKeyRequest,
    PublicKeyResponse,
    KeyUploadResponse,
)

from app.services.key_service import (
    KeyService,
)

router = APIRouter(
    prefix="/keys",
    tags=["Encryption Keys"],
)


# ==========================================================
# Upload Public Key
# ==========================================================

@router.post(
    "/public",
    response_model=KeyUploadResponse,
)
async def upload_public_key(
    request: UploadPublicKeyRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):

    repository = UserKeyRepository(db)

    service = KeyService(repository)

    return await service.upload_public_key(
        current_user=current_user,
        public_key=request.public_key,
    )


# ==========================================================
# Get Public Key
# ==========================================================

@router.get(
    "/{user_id}",
    response_model=PublicKeyResponse,
)
async def get_public_key(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
):

    repository = UserKeyRepository(db)

    service = KeyService(repository)

    return await service.get_public_key(
        user_id=user_id,
    )