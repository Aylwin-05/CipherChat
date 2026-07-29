from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    UploadFile,
)
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db
from app.dependencies.auth import get_current_user
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
)
async def upload_attachment(
    message_id: UUID,
    file: UploadFile = File(...),
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

    if not allowed:

        raise HTTPException(
            status_code=403,
            detail="Access denied.",
        )

    attachment = await attachment_service.upload_attachment(
        message.id,
        file,
    )
    print(attachment.attachment_type)
    print(attachment.mime_type)
    await db.commit()
    await db.refresh(attachment)

    print("AFTER COMMIT")
    print("Attachment ID:", attachment.id)
    print("Attachment object:", attachment)
    print("Attachment ID:", attachment.id)
    print("Message ID:", attachment.message_id)
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

                "download_url":
                    f"/api/v1/attachments/{attachment.id}",

                "created_at":
                    attachment.created_at.isoformat(),
            },
        },
    )

    return UploadResponse(
        success=True,
        message="File uploaded successfully.",
        attachment=AttachmentResponse.model_validate(
            attachment
        ),
    )


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

    return FileResponse(
        path=attachment.storage_path,
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