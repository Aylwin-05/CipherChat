from uuid import uuid4

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class Conversation(Base):
    """
    Represents a chat conversation.

    - private: exactly two participants
    - group: many participants, shared by all members
    """

    __tablename__ = "conversations"

    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    name: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    conversation_type: Mapped[str] = mapped_column(
        String(20),
        default="private",
        nullable=False,
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

    # Disappearing messages: seconds after send before the
    # server erases the ciphertext (None = disabled).
    disappear_after_seconds: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )