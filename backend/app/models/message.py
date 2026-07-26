from uuid import uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class Message(Base):
    """
    End-to-End Encrypted Message

    Server NEVER stores plaintext.

    Stored:
        ciphertext
        encrypted AES key
        nonce

    Plaintext exists only on client devices.
    """

    __tablename__ = "messages"

    # ==========================================================
    # Identity
    # ==========================================================

    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    conversation_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "conversations.id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )

    sender_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "users.id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )

    # ==========================================================
    # Encrypted Payload
    # ==========================================================

    ciphertext: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )

    encrypted_key_sender: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )

    encrypted_key_receiver: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )

    nonce: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )

    # ==========================================================
    # Metadata
    # ==========================================================

    message_type: Mapped[str] = mapped_column(
        String(30),
        default="text",
        nullable=False,
    )

    crypto_version: Mapped[int] = mapped_column(
        default=1,
        nullable=False,
    )

    reply_to_id: Mapped[UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "messages.id",
            ondelete="SET NULL",
        ),
        nullable=True,
    )

    edited: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    deleted_for_everyone: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    is_read: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    delivered_at: Mapped[DateTime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    read_at: Mapped[DateTime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    updated_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )