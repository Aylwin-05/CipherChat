from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# ==========================================================
# Send Message Request
# ==========================================================

class SendMessageRequest(BaseModel):
    """
    Request body for sending a message.
    """

    conversation_id: UUID
    content: str = Field(
        min_length=1,
        max_length=5000,
    )


# ==========================================================
# Message Response
# ==========================================================

class MessageResponse(BaseModel):
    """
    Message returned to clients.
    """

    model_config = ConfigDict(
        from_attributes=True,
    )

    id: UUID
    conversation_id: UUID
    sender_id: UUID
    content: str
    is_read: bool
    created_at: datetime