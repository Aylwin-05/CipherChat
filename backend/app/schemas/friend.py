from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


# ==========================================================
# Send Friend Request
# ==========================================================

class SendFriendRequest(BaseModel):
    """
    Request body for sending a friend request.
    """

    receiver_id: UUID


# ==========================================================
# Respond to Friend Request
# ==========================================================

class FriendRequestAction(BaseModel):
    """
    Accept or reject a friend request.
    """

    friendship_id: UUID


# ==========================================================
# Friend Response
# ==========================================================

class FriendResponse(BaseModel):
    """
    Friend request response model.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    sender_id: UUID
    receiver_id: UUID
    status: str
    created_at: datetime


# ==========================================================
# Simple Message
# ==========================================================

class FriendMessage(BaseModel):
    """
    Standard response message.
    """

    success: bool
    message: str