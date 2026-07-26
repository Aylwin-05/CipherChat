from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.attachment import AttachmentResponse


# ==========================================================
# SEND MESSAGE
# ==========================================================

class SendMessageRequest(BaseModel):
    """
    Encrypted message request.

    The backend never receives plaintext.
    """

    conversation_id: UUID

    ciphertext: str = Field(
        min_length=1,
    )

    encrypted_key_sender: str = Field(
        min_length=1,
    )

    encrypted_key_receiver: str = Field(
        min_length=1,
    )

    nonce: str = Field(
        min_length=1,
    )

    message_type: str = Field(
        default="text",
        max_length=30,
    )

    reply_to_id: UUID | None = None


# ==========================================================
# EDIT MESSAGE
# ==========================================================

class EditMessageRequest(BaseModel):
    """
    Edit an existing message.
    """

    content: str = Field(
        min_length=1,
        max_length=5000,
    )


# ==========================================================
# DELETE MESSAGE
# ==========================================================

class DeleteMessageRequest(BaseModel):
    """
    Delete message for everyone.
    """

    message_id: UUID


# ==========================================================
# MESSAGE RESPONSE
# ==========================================================

class MessageResponse(BaseModel):

    model_config = ConfigDict(
        from_attributes=True,
    )

    id: UUID

    conversation_id: UUID

    sender_id: UUID

    # ======================================================
    # Encrypted Payload
    # ======================================================

    ciphertext: str

    encrypted_key_sender: str
    encrypted_key_receiver: str

    nonce: str

    crypto_version: int

    # ======================================================
    # Metadata
    # ======================================================

    message_type: str

    reply_to_id: UUID | None

    edited: bool

    deleted_for_everyone: bool

    is_read: bool

    delivered_at: datetime | None

    read_at: datetime | None

    created_at: datetime

    updated_at: datetime

    attachments: list[AttachmentResponse] = []


# ==========================================================
# MESSAGE LIST
# ==========================================================

class MessageListResponse(BaseModel):

    messages: list[MessageResponse]