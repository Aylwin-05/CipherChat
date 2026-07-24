from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db
from app.repositories.auth_repository import AuthRepository
from app.services.jwt_service import JWTService

security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
):

    token = credentials.credentials

    print("\n========== AUTH ==========")
    print("Token:", token[:40] + "...")

    jwt_service = JWTService()

    payload = jwt_service.verify_access_token(token)

    print("Payload:", payload)

    if payload is None:
        print("FAILED -> Invalid token")

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token.",
        )

    user_id = payload.get("sub")

    print("User ID:", user_id)

    if user_id is None:
        print("FAILED -> Missing sub")

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload.",
        )

    repository = AuthRepository(db)

    user = await repository.get_user_by_id(
        UUID(user_id)
    )

    print("User:", user)

    if user is None:

        print("FAILED -> User not found")

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found.",
        )

    print("AUTH SUCCESS")

    return user