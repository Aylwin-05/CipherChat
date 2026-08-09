from uuid import UUID
from datetime import datetime
from pathlib import Path
from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
)
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
import logging

logger = logging.getLogger(__name__)
from app.database.session import get_db
from app.dependencies.auth import get_current_user
from app.dependencies.rate_limit import rate_limit
from app.models.user import User
from app.repositories.attachment_repository import AttachmentRepository
from app.repositories.conversation_repository import (
    ConversationRepository,
)
from app.repositories.message_repository import (
    MessageRepository,
)
from app.schemas.attachment import (
    AttachmentResponse,
    UploadResponse,
)
from app.services.attachment_service import AttachmentService
from app.websocket.connection_manager import manager

router = APIRouter(
    prefix="/attachments",
    tags=["Attachments"],
)


# ==========================================================
# Upload Attachment
# ==========================================================

@router.post(
    "/upload/{message_id}",
    response_model=UploadResponse,
    dependencies=[
        rate_limit("attachments.upload", 10, 60),
    ],
)
async def upload_attachment(
    message_id: UUID,

    file: UploadFile = File(...),

    encrypted: bool = Form(False),

    encrypted_key_sender: str | None = Form(None),

    encrypted_key_receiver: str | None = Form(None),

    nonce: str | None = Form(None),

    current_user: User = Depends(get_current_user),

    db: AsyncSession = Depends(get_db),
):

    attachment_repository = AttachmentRepository(db)

    message_repository = MessageRepository(db)

    conversation_repository = ConversationRepository(db)

    attachment_service = AttachmentService(
        attachment_repository,
    )

    message = await message_repository.get_by_id(
        message_id
    )

    if message is None:

        raise HTTPException(
            status_code=404,
            detail="Message not found.",
        )

    participants = (
        await conversation_repository.get_participants(
            message.conversation_id
        )
    )

    allowed = any(
        participant.user_id == current_user.id
        for participant in participants
    )

    if encrypted:

        if not encrypted_key_sender:
            raise HTTPException(
                status_code=400,
                detail="Missing sender encrypted key.",
            )

        if not encrypted_key_receiver:
            raise HTTPException(
                status_code=400,
                detail="Missing receiver encrypted key.",
            )

        if not nonce:
            raise HTTPException(
                status_code=400,
                detail="Missing encryption nonce.",
            )
    try:
        attachment = await attachment_service.upload_attachment(
            message.id,
            file,
            encrypted=encrypted,
            encrypted_key_sender=encrypted_key_sender,
            encrypted_key_receiver=encrypted_key_receiver,
            nonce=nonce,
        )

    except Exception as e:
        logger.exception("Attachment upload failed")
        raise

    await db.commit()

    await db.refresh(attachment)

    # ==========================================================
    # Broadcast Attachment
    # ==========================================================

    await manager.broadcast(
        message.conversation_id,
        {
            "event": "attachment",

            "message_id": str(
                message.id
            ),

            "conversation_id": str(
                message.conversation_id
            ),

            "sender_id": str(
                current_user.id
            ),

            "attachment": {

                "id": str(
                    attachment.id
                ),

                "original_name":
                    attachment.original_name,

                "filename":
                    attachment.filename,

                "attachment_type":
                    attachment.attachment_type,

                "mime_type":
                    attachment.mime_type,

                "extension":
                    attachment.extension,

                "size":
                    attachment.size,

                "encrypted":
                    attachment.encrypted,

                "encrypted_key_sender":
                    attachment.encrypted_key_sender,

                "encrypted_key_receiver":
                    attachment.encrypted_key_receiver,

                "nonce":
                    attachment.nonce,

                "download_url":
                    f"/api/v1/attachments/{attachment.id}",

                "created_at":
                    attachment.created_at.isoformat(),
            },
        },
    )

    return {
        "success": True,
        "message": "Attachment uploaded successfully.",
        "attachment": attachment,
    }


# ==========================================================
# Download Attachment
# ==========================================================

@router.get(
    "/{attachment_id}",
)
async def download_attachment(
    attachment_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):

    attachment_repository = AttachmentRepository(db)

    message_repository = MessageRepository(db)

    conversation_repository = ConversationRepository(db)

    attachment_service = AttachmentService(
        attachment_repository,
    )

    attachment = await attachment_service.get_attachment(
        attachment_id
    )

    if attachment is None:

        raise HTTPException(
            status_code=404,
            detail="Attachment not found.",
        )

    message = await message_repository.get_by_id(
        attachment.message_id
    )

    if message is None:

        raise HTTPException(
            status_code=404,
            detail="Message not found.",
        )

    participants = (
        await conversation_repository.get_participants(
            message.conversation_id
        )
    )

    allowed = any(
        participant.user_id == current_user.id
        for participant in participants
    )

    if not allowed:

        raise HTTPException(
            status_code=403,
            detail="Access denied.",
        )

    file_path = Path(attachment.storage_path)

    if not file_path.exists():

        raise HTTPException(
            status_code=404,
            detail="Attachment file not found.",
        )

    return FileResponse(
        path=file_path,
        filename=attachment.original_name,
        media_type=attachment.mime_type,
    )


# ==========================================================
# Delete Attachment
# ==========================================================

@router.delete(
    "/{attachment_id}",
)
async def delete_attachment(
    attachment_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):

    attachment_repository = AttachmentRepository(db)

    message_repository = MessageRepository(db)

    conversation_repository = ConversationRepository(db)

    attachment_service = AttachmentService(
        attachment_repository,
    )

    attachment = await attachment_service.get_attachment(
        attachment_id
    )

    if attachment is None:

        raise HTTPException(
            status_code=404,
            detail="Attachment not found.",
        )

    message = await message_repository.get_by_id(
        attachment.message_id
    )

    if message is None:

        raise HTTPException(
            status_code=404,
            detail="Message not found.",
        )

    participants = (
        await conversation_repository.get_participants(
            message.conversation_id
        )
    )

    allowed = any(
        participant.user_id == current_user.id
        for participant in participants
    )

    if not allowed:

        raise HTTPException(
            status_code=403,
            detail="Access denied.",
        )

    deleted = await attachment_service.delete_attachment(
        attachment_id
    )

    if not deleted:
    
        raise HTTPException(
            status_code=404,
            detail="Attachment not found.",
        )
    await db.commit()
    # ==========================================================
    # Broadcast Delete
    # ==========================================================

    await manager.broadcast(
        message.conversation_id,
        {
            "event": "attachment_deleted",
            "attachment_id": str(
                attachment.id
            ),
            "message_id": str(
                message.id
            ),
        },
    )

    return {
        "success": True,
        "message": "Attachment deleted successfully.",
    }