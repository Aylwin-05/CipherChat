from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


# ==========================================================
# Attachment Response
# ==========================================================

class AttachmentResponse(BaseModel):

    model_config = ConfigDict(
        from_attributes=True,
    )

    id: UUID

    message_id: UUID

    original_name: str

    filename: str

    mime_type: str

    extension: str

    attachment_type: str

    size: int

    storage_path: str

    created_at: datetime

    updated_at: datetime


# ==========================================================
# Upload Response
# ==========================================================

class UploadResponse(BaseModel):

    success: bool

    message: str

    attachment: AttachmentResponse