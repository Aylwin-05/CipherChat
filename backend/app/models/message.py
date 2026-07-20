from uuid import uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class Message(Base):
    """
    Represents a chat message.

    Lifecycle:

    Created
        ↓
    Delivered
        ↓
    Read

    Future:
    - End-to-End Encryption
    - Reply
    - Forward
    - Reactions
    - Attachments
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
    # Message
    # ==========================================================

    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    message_type: Mapped[str] = mapped_column(
        String(20),
        default="text",
        nullable=False,
    )

    # ==========================================================
    # Delivery Status
    # ==========================================================

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

    # ==========================================================
    # Audit
    # ==========================================================

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