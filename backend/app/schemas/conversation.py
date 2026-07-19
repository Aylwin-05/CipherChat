from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


# ==========================================================
# Create/Open Conversation
# ==========================================================

class CreateConversationRequest(BaseModel):
    """
    Request to create or open a conversation.
    """

    user_id: UUID


# ==========================================================
# Conversation Response
# ==========================================================

class ConversationResponse(BaseModel):
    """
    Conversation response.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
    updated_at: datetime