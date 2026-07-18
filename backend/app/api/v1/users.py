from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.user import (
    SearchUserResponse,
    UpdateProfileRequest,
    UserResponse,
    UsernameAvailabilityResponse,
)
from app.services.user_service import UserService

router = APIRouter(
    prefix="/users",
    tags=["Users"],
)


# ==========================================================
# Get My Profile
# ==========================================================

@router.get(
    "/me",
    response_model=UserResponse,
)
async def get_my_profile(
    current_user: User = Depends(get_current_user),
):
    """
    Return the authenticated user's profile.
    """

    return current_user


# ==========================================================
# Update My Profile
# ==========================================================

@router.patch(
    "/me",
    response_model=UserResponse,
)
async def update_my_profile(
    request: UpdateProfileRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    repository = UserRepository(db)
    service = UserService(repository)

    updated_user = await service.update_profile(
        current_user,
        request,
    )

    return updated_user


# ==========================================================
# Search Users
# ==========================================================

@router.get(
    "/search",
    response_model=list[SearchUserResponse],
)
async def search_users(
    q: str = Query(
        ...,
        min_length=1,
        description="Username or display name",
    ),
    db: AsyncSession = Depends(get_db),
):
    repository = UserRepository(db)
    service = UserService(repository)

    users = await service.search_users(q)

    return users


# ==========================================================
# Check Username Availability
# ==========================================================

@router.get(
    "/check-username",
    response_model=UsernameAvailabilityResponse,
)
async def check_username(
    username: str = Query(
        ...,
        min_length=3,
        max_length=30,
    ),
    db: AsyncSession = Depends(get_db),
):
    repository = UserRepository(db)
    service = UserService(repository)

    available = await service.is_username_available(
        username
    )

    if available:
        return UsernameAvailabilityResponse(
            available=True,
            message="Username is available.",
        )

    return UsernameAvailabilityResponse(
        available=False,
        message="Username already exists.",
    )