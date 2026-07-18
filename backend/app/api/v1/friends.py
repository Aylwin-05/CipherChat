from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.repositories.friend_repository import FriendRepository
from app.schemas.friend import (
    FriendMessage,
    FriendRequestAction,
    FriendResponse,
    SendFriendRequest,
)
from app.services.friend_service import FriendService

router = APIRouter(
    prefix="/friends",
    tags=["Friends"],
)


# ==========================================================
# Send Friend Request
# ==========================================================

@router.post(
    "/request",
    response_model=FriendResponse,
)
async def send_friend_request(
    request: SendFriendRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    repository = FriendRepository(db)
    service = FriendService(repository)

    try:
        friendship = await service.send_request(
            current_user,
            request.receiver_id,
        )

        return friendship

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


# ==========================================================
# Pending Requests
# ==========================================================

@router.get(
    "/pending",
    response_model=list[FriendResponse],
)
async def get_pending_requests(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    repository = FriendRepository(db)
    service = FriendService(repository)

    return await service.pending_requests(current_user)


# ==========================================================
# Friends List
# ==========================================================

@router.get(
    "/",
    response_model=list[FriendResponse],
)
async def get_friends(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    repository = FriendRepository(db)
    service = FriendService(repository)

    return await service.friends(current_user)


# ==========================================================
# Accept Request
# ==========================================================

@router.post(
    "/accept",
    response_model=FriendResponse,
)
async def accept_friend_request(
    request: FriendRequestAction,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    repository = FriendRepository(db)
    service = FriendService(repository)

    try:
        return await service.accept_request(
            request.friendship_id,
            current_user,
        )

    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=str(e),
        )


# ==========================================================
# Reject Request
# ==========================================================

@router.post(
    "/reject",
    response_model=FriendMessage,
)
async def reject_friend_request(
    request: FriendRequestAction,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    repository = FriendRepository(db)
    service = FriendService(repository)

    try:
        await service.reject_request(
            request.friendship_id,
            current_user,
        )

        return FriendMessage(
            success=True,
            message="Friend request rejected.",
        )

    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=str(e),
        )


# ==========================================================
# Remove Friend
# ==========================================================

@router.delete(
    "/{friendship_id}",
    response_model=FriendMessage,
)
async def remove_friend(
    friendship_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    repository = FriendRepository(db)
    service = FriendService(repository)

    try:
        from uuid import UUID

        await service.remove_friend(
            UUID(friendship_id),
            current_user,
        )

        return FriendMessage(
            success=True,
            message="Friend removed successfully.",
        )

    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=str(e),
        )