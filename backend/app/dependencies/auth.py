from uuid import UUID

from app.database.session import get_db
from app.repositories.auth_repository import AuthRepository
from app.services.jwt_service import JWTService
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
):

    token = credentials.credentials

    jwt_service = JWTService()

    payload = jwt_service.verify_access_token(token)

    if payload is None:

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token.",
        )

    user_id = payload.get("sub")

    if user_id is None:

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload.",
        )

    repository = AuthRepository(db)

    user = await repository.get_user_by_id(
        UUID(user_id)
    )

    if user is None:

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found.",
        )

    if not getattr(user, "is_active", True):

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated.",
        )

    return user
