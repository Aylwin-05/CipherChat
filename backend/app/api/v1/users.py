from pathlib import Path
from uuid import UUID
import mimetypes

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Query,
    UploadFile,
)
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.file_config import (
    AVATAR_DIR,
    AVATAR_EXTENSIONS,
    MAX_AVATAR_SIZE,
)
from app.core.enums import FriendRequestStatus
from app.database.session import get_db
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.repositories.friend_repository import FriendRepository
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

    await repository.commit()

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
        description="Search by email",
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


# ==========================================================
# Upload Avatar
# ==========================================================

@router.post(
    "/avatar",
    response_model=UserResponse,
)
async def upload_avatar(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Upload the authenticated user's avatar image.

    The image is stored on disk and served only to the user
    and their friends via ``GET /users/{user_id}/avatar``.
    """

    filename = file.filename or ""
    extension = Path(filename).suffix.lower()

    if extension not in AVATAR_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail="Unsupported image type.",
        )

    content = await file.read()

    if len(content) > MAX_AVATAR_SIZE:
        raise HTTPException(
            status_code=413,
            detail="Avatar image is too large (max 5 MB).",
        )

    if not content:
        raise HTTPException(
            status_code=400,
            detail="Empty file.",
        )

    # --------------------------------------------------------
    # Replace any previous avatar for this user
    # --------------------------------------------------------

    for old_file in AVATAR_DIR.glob(f"{current_user.id}.*"):
        old_file.unlink(missing_ok=True)

    destination = AVATAR_DIR / f"{current_user.id}{extension}"

    destination.write_bytes(content)

    repository = UserRepository(db)

    current_user.avatar_url = f"/api/v1/users/{current_user.id}/avatar"

    await repository.update_user(current_user)

    await repository.commit()

    return current_user


# ==========================================================
# Get Avatar (self or friends only)
# ==========================================================

@router.get(
    "/{user_id}/avatar",
)
async def get_avatar(
    user_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Serve a user's avatar image.

    Only the owner and accepted friends may view it; other
    users get a 404 so presence of an avatar is not leaked.
    """

    repository = UserRepository(db)

    target_user = await repository.get_by_id(user_id)

    if target_user is None:
        raise HTTPException(
            status_code=404,
            detail="User not found.",
        )

    if target_user.id != current_user.id:

        friend_repository = FriendRepository(db)

        friendship = await friend_repository.get_existing_friendship(
            current_user.id,
            target_user.id,
        )

        is_friend = (
            friendship is not None
            and friendship.status == FriendRequestStatus.ACCEPTED.value
        )

        if not is_friend:
            raise HTTPException(
                status_code=404,
                detail="Not found.",
            )

    avatar_files = list(AVATAR_DIR.glob(f"{target_user.id}.*"))

    if not avatar_files:
        raise HTTPException(
            status_code=404,
            detail="Avatar not found.",
        )

    file_path = avatar_files[0]

    media_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"

    return FileResponse(
        path=file_path,
        media_type=media_type,
    )