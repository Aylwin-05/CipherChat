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
    Message returned by the API.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    conversation_id: UUID
    sender_id: UUID
    content: str
    message_type: str
    created_at: datetime