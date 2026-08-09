from base64 import b64encode
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db
from app.dependencies.auth import get_current_user
from app.dependencies.rate_limit import rate_limit
from app.models.user import User
from app.repositories.attachment_repository import AttachmentRepository
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.message_repository import MessageRepository
from app.schemas.message import (
    MessageResponse,
    SendMessageRequest,
)
from app.services.attachment_service import AttachmentService
from app.services.message_service import MessageService

router = APIRouter(
    prefix="/messages",
    tags=["Messages"],
)
from app.schemas.attachment import AttachmentResponse

# ==========================================================
# Convert DB model -> API response
# ==========================================================
def serialize_message(message):

    attachments = [    {
        "id": attachment.id,
        "original_name": attachment.original_name,
        "filename": attachment.filename,
        "mime_type": attachment.mime_type,
        "attachment_type": attachment.attachment_type,
        "extension": attachment.extension,
        "size": attachment.size,
        "download_url": f"/api/v1/attachments/{attachment.id}",
        "created_at": attachment.created_at,
        "encrypted": attachment.encrypted,
        "encrypted_key_sender": attachment.encrypted_key_sender,
        "encrypted_key_receiver": attachment.encrypted_key_receiver,
        "nonce": attachment.nonce,
    }
    for attachment in message.attachments]

    # Only serialize if SQLAlchemy has already loaded them
    if "attachments" in message.__dict__:
        attachments = [
            AttachmentResponse.model_validate(a)
            for a in message.attachments
        ]

    return MessageResponse(
        id=message.id,
        conversation_id=message.conversation_id,
        sender_id=message.sender_id,

        ciphertext=message.ciphertext,
        encrypted_key_sender=message.encrypted_key_sender,
        encrypted_key_receiver=message.encrypted_key_receiver,
        nonce=message.nonce,
        crypto_version=message.crypto_version,

        message_type=message.message_type,
        reply_to_id=message.reply_to_id,

        edited=message.edited,
        deleted_for_everyone=message.deleted_for_everyone,

        is_read=message.is_read,
        delivered_at=message.delivered_at,
        read_at=message.read_at,

        created_at=message.created_at,
        updated_at=message.updated_at,

        attachments=attachments,
    )


# ==========================================================
# SEND ENCRYPTED MESSAGE
# ==========================================================

@router.post(
    "/send",
    response_model=MessageResponse,
    dependencies=[
        rate_limit("messages.send", 60, 60),
    ],
)
async def send_message(
    request: SendMessageRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):

    message_repository = MessageRepository(db)
    conversation_repository = ConversationRepository(db)
    attachment_repository = AttachmentRepository(db)

    attachment_service = AttachmentService(
        attachment_repository
    )

    service = MessageService(
        message_repository,
        conversation_repository,
        attachment_service,
    )

    try:

        message = await service.send_message(
            current_user=current_user,
            conversation_id=request.conversation_id,
            ciphertext=request.ciphertext,
            encrypted_key_sender=request.encrypted_key_sender,
            encrypted_key_receiver=request.encrypted_key_receiver,
            nonce=request.nonce,
            message_type=request.message_type,
            reply_to_id=request.reply_to_id,
        )

        await db.commit()

        await db.refresh(
        message,
        [
            "attachments"
        ]
        )

        return serialize_message(message)

    except ValueError as e:

        await db.rollback()

        raise HTTPException(
            status_code=400,
            detail=str(e),
        )


# ==========================================================
# GET CONVERSATION MESSAGES
# ==========================================================

@router.get(
    "/{conversation_id}",
    response_model=list[MessageResponse],
    dependencies=[
        rate_limit("messages.history", 120, 60),
    ],
)
async def get_messages(
    conversation_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):

    message_repository = MessageRepository(db)
    conversation_repository = ConversationRepository(db)
    attachment_repository = AttachmentRepository(db)

    attachment_service = AttachmentService(
        attachment_repository
    )

    service = MessageService(
        message_repository,
        conversation_repository,
        attachment_service,
    )

    try:

        messages = await service.get_messages(
            current_user=current_user,
            conversation_id=conversation_id,
        )

        return [
            serialize_message(message)
            for message in messages
        ]

    except ValueError as e:

        raise HTTPException(
            status_code=400,
            detail=str(e),
        )