from uuid import UUID

from app.core.enums import FriendRequestStatus
from app.models.friendship import Friendship
from app.models.user import User
from app.repositories.friend_repository import FriendRepository


class FriendService:
    """
    Business logic for friendships.
    """

    def __init__(self, repository: FriendRepository):
        self.repository = repository

    # ==========================================================
    # Send Friend Request
    # ==========================================================

    async def send_request(
        self,
        sender: User,
        receiver_id: UUID,
    ) -> Friendship:

        # Cannot send request to yourself
        if sender.id == receiver_id:
            raise ValueError(
                "You cannot send a friend request to yourself."
            )

        # Check for existing friendship/request
        existing = await self.repository.get_existing_friendship(
            sender.id,
            receiver_id,
        )

        if existing:
            raise ValueError(
                "Friend request already exists."
            )

        friendship = Friendship(
            sender_id=sender.id,
            receiver_id=receiver_id,
            status=FriendRequestStatus.PENDING.value,
        )

        return await self.repository.create_request(
            friendship
        )

    # ==========================================================
    # Accept Request
    # ==========================================================

    async def accept_request(
        self,
        friendship_id: UUID,
        current_user: User,
    ) -> Friendship:

        friendship = await self.repository.get_by_id(
            friendship_id
        )

        if friendship is None:
            raise ValueError(
                "Friend request not found."
            )

        if friendship.receiver_id != current_user.id:
            raise ValueError(
                "Not authorized."
            )

        friendship.status = (
            FriendRequestStatus.ACCEPTED.value
        )

        await self.repository.save()

        return friendship

    # ==========================================================
    # Reject Request
    # ==========================================================

    async def reject_request(
        self,
        friendship_id: UUID,
        current_user: User,
    ):

        friendship = await self.repository.get_by_id(
            friendship_id
        )

        if friendship is None:
            raise ValueError(
                "Friend request not found."
            )

        if friendship.receiver_id != current_user.id:
            raise ValueError(
                "Not authorized."
            )

        friendship.status = (
            FriendRequestStatus.REJECTED.value
        )

        await self.repository.save()

    # ==========================================================
    # Remove Friend
    # ==========================================================

    async def remove_friend(
        self,
        friendship_id: UUID,
        current_user: User,
    ):

        friendship = await self.repository.get_by_id(
            friendship_id
        )

        if friendship is None:
            raise ValueError(
                "Friendship not found."
            )

        if (
            friendship.sender_id != current_user.id
            and friendship.receiver_id != current_user.id
        ):
            raise ValueError(
                "Not authorized."
            )

        await self.repository.remove(friendship)

    # ==========================================================
    # Pending Requests
    # ==========================================================

    async def pending_requests(
        self,
        current_user: User,
    ):
        return await self.repository.get_pending_requests(
            current_user.id
        )

    # ==========================================================
    # Friends List
    # ==========================================================

    async def friends(
        self,
        current_user: User,
    ):
        return await self.repository.get_friends(
            current_user.id
        )