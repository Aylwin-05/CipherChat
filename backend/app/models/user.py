import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Index,
    String,
    Text,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import OnlineStatus
from app.database.base import Base
from app.database.mixins import TimestampMixin


class User(Base, TimestampMixin):
    """
    Primary user model for CipherChat.
    """

    __tablename__ = "users"

    __table_args__ = (
        Index("ix_users_email", "email"),
        Index("ix_users_username", "username"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
        comment="Primary UUID identifier.",
    )

    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        comment="User email used for OTP authentication.",
    )

    username: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        nullable=False,
        comment="Unique public username.",
    )

    display_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="User display name.",
    )

    bio: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Optional user biography.",
    )

    avatar_url: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        comment="Profile picture URL.",
    )

    public_key: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Public encryption key used for end-to-end encryption.",
    )

    is_verified: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        comment="Email verification status.",
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        comment="Whether the account is active.",
    )

    online_status: Mapped[str] = mapped_column(
        String(20),
        default=OnlineStatus.OFFLINE.value,
        nullable=False,
        comment="Current user presence status.",
    )

    last_seen: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Last active timestamp.",
    )

    def __repr__(self) -> str:
        return (
            f"<User(id={self.id}, "
            f"username='{self.username}', "
            f"email='{self.email}')>"
        )