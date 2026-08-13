from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# ==========================================================
# Create Conversation
# ==========================================================

class CreateConversationRequest(BaseModel):
    user_id: UUID


# ==========================================================
# Create Group
# ==========================================================

class CreateGroupRequest(BaseModel):

    name: str = Field(
        min_length=1,
        max_length=100,
    )

    member_ids: list[UUID] = Field(
        min_length=1,
        max_length=49,
    )


# ==========================================================
# Add Group Members
# ==========================================================

class AddGroupMembersRequest(BaseModel):

    member_ids: list[UUID] = Field(
        min_length=1,
        max_length=49,
    )


# ==========================================================
# Update Conversation Settings (pin / archive / mute)
# ==========================================================

class UpdateConversationSettingsRequest(BaseModel):

    is_pinned: bool | None = None

    is_archived: bool | None = None

    muted_until: datetime | None = None

    disappear_after_seconds: int | None = None


# ==========================================================
# Create Conversation Response
# ==========================================================

class ConversationCreateResponse(BaseModel):

    model_config = ConfigDict(
        from_attributes=True,
    )

    id: UUID
    created_at: datetime
    updated_at: datetime


# ==========================================================
# Other User
# ==========================================================

class ConversationUser(BaseModel):

    model_config = ConfigDict(
        from_attributes=True,
    )

    id: UUID
    display_name: str
    username: str
    email: str
    avatar_url: str | None
    online_status: str


# ==========================================================
# Last Message
# ==========================================================

class LastMessage(BaseModel):

    ciphertext: str | None = None

    message_type: str | None = None

    created_at: datetime | None = None


# ==========================================================
# Conversation List Response
# ==========================================================

class ConversationResponse(BaseModel):

    id: UUID

    updated_at: datetime

    conversation_type: str = "private"

    name: str | None = None

    participant_count: int | None = None

    other_user: ConversationUser | None = None

    last_message: LastMessage | None = None

    unread_count: int = 0

    is_pinned: bool = False

    is_archived: bool = False

    muted: bool = False

    disappear_after_seconds: int | None = None

    delete_requested_by: UUID | None = None

    delete_requested_at: datetime | None = None