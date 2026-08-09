from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


# ==========================================================
# Create Conversation
# ==========================================================

class CreateConversationRequest(BaseModel):
    user_id: UUID


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

    other_user: ConversationUser

    last_message: LastMessage | None = None

    unread_count: int = 0