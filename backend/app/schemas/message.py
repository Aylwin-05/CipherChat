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

    is_forwarded: bool = False

    # NEW
    attachment_ids: list[UUID] = []

    # Per-recipient wrapped AES key copies (group chats).
    # One entry per member, keyed by public key at creation time.
    recipient_keys: list["RecipientKeyInput"] = []

    # Per-device Signal envelopes (multi-device E2EE).
    # One entry per device of every participant; a device can
    # only decrypt its own copy.
    envelopes: list["MessageEnvelopeInput"] = []


# ==========================================================
# PER-DEVICE ENVELOPE (multi-device E2EE)
# ==========================================================

class MessageEnvelopeInput(BaseModel):

    device_id: str = Field(
        min_length=8,
        max_length=64,
    )

    data: str = Field(
        min_length=1,
    )


# ==========================================================
# PER-RECIPIENT MESSAGE KEY (group E2EE)
# ==========================================================

class RecipientKeyInput(BaseModel):

    user_id: UUID

    encrypted_key: str = Field(
        min_length=1,
    )


# ==========================================================
# EDIT MESSAGE
# ==========================================================

class EditMessageRequest(BaseModel):
    """
    Edit an existing message.

    End-to-end encrypted: like a fresh send, the edited content
    is encrypted client-side and the server only receives the
    new ciphertext + wrapped keys. The server never sees the
    edited plaintext.
    """

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

    recipient_keys: list["RecipientKeyInput"] = []

    envelopes: list["MessageEnvelopeInput"] = []


# ==========================================================
# REACTION
# ==========================================================

class ReactionRequest(BaseModel):
    """
    Toggle an emoji reaction on a message.
    """

    emoji: str = Field(
        min_length=1,
        max_length=32,
    )


class ReactionResponse(BaseModel):

    model_config = ConfigDict(
        from_attributes=True,
    )

    user_id: UUID

    emoji: str

    created_at: datetime


# ==========================================================
# PER-RECIPIENT KEY RESPONSE
# ==========================================================

class RecipientKeyResponse(BaseModel):

    user_id: UUID

    encrypted_key: str


# ==========================================================
# PER-DEVICE ENVELOPE RESPONSE
# ==========================================================

class MessageEnvelopeResponse(BaseModel):

    device_id: str

    data: str


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

    is_forwarded: bool

    deleted_for_everyone: bool

    is_read: bool

    delivered_at: datetime | None

    read_at: datetime | None

    expires_at: datetime | None

    created_at: datetime

    updated_at: datetime

    attachments: list[AttachmentResponse] = []

    reactions: list[ReactionResponse] = []

    recipient_keys: list[RecipientKeyResponse] = []

    envelopes: list[MessageEnvelopeResponse] = []


# ==========================================================
# MESSAGE LIST
# ==========================================================

class MessageListResponse(BaseModel):

    messages: list[MessageResponse]