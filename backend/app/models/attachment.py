from uuid import uuid4

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import (
    Mapped,
    mapped_column,
    relationship,
)

from app.database.base import Base


class Attachment(Base):
    """
    Stores metadata for uploaded files.

    A single message may contain multiple attachments.

    Supported:
    - Images
    - Videos
    - Documents
    - Audio
    - Voice Notes
    - Archives

    Future:
    - Cloud Storage (AWS S3 / MinIO)
    - Encrypted Files
    - Image Compression
    - Video Compression
    - Thumbnail Generation
    """

    __tablename__ = "attachments"

    # ==========================================================
    # Identity
    # ==========================================================

    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    # ==========================================================
    # Relationships
    # ==========================================================

    message_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "messages.id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )

    # ==========================================================
    # File Information
    # ==========================================================

    original_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    filename: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
    )

    mime_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    extension: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )

    attachment_type: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )

    size: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )

    storage_path: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )

    # ==========================================================
    # Optional Media Metadata
    # ==========================================================

    thumbnail_path: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    width: Mapped[int | None] = mapped_column(
        nullable=True,
    )

    height: Mapped[int | None] = mapped_column(
        nullable=True,
    )

    duration: Mapped[float | None] = mapped_column(
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

    # ==========================================================
    # SQLAlchemy Relationships
    # ==========================================================

    message: Mapped["Message"] = relationship(
        "Message",
        backref="attachments",
    )

    # ==========================================================
    # Representation
    # ==========================================================

    def __repr__(self) -> str:
        return (
            f"<Attachment("
            f"id={self.id}, "
            f"type={self.attachment_type}, "
            f"filename='{self.filename}'"
            f")>"
        )