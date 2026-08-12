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
    EditMessageRequest,
    MessageResponse,
    ReactionRequest,
    ReactionResponse,
    SendMessageRequest,
)
from app.services.attachment_service import AttachmentService
from app.services.message_service import MessageService
from app.websocket.connection_manager import manager

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
        is_forwarded=message.is_forwarded,
        deleted_for_everyone=message.deleted_for_everyone,

        is_read=message.is_read,
        delivered_at=message.delivered_at,
        read_at=message.read_at,
        expires_at=message.expires_at,

        created_at=message.created_at,
        updated_at=message.updated_at,

        attachments=attachments,

        reactions=[
            ReactionResponse(
                user_id=reaction.user_id,
                emoji=reaction.emoji,
                created_at=reaction.created_at,
            )
            for reaction in message.reactions
        ],
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
            is_forwarded=request.is_forwarded,
        )

        await db.commit()

        await db.refresh(
        message,
        [
            "attachments",
            "reactions",
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
# EDIT ENCRYPTED MESSAGE
#
# The edited plaintext never reaches the backend: the client
# re-encrypts it (Signal ratchet) and sends the new ciphertext
# + wrapped keys, exactly like a fresh send.
# ==========================================================

@router.put(
    "/{message_id}/edit",
    response_model=MessageResponse,
    dependencies=[
        rate_limit("messages.edit", 30, 60),
    ],
)
async def edit_message(
    message_id: UUID,
    request: EditMessageRequest,
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

        message = await service.edit_message(
            current_user=current_user,
            message_id=message_id,
            ciphertext=request.ciphertext,
            encrypted_key_sender=request.encrypted_key_sender,
            encrypted_key_receiver=request.encrypted_key_receiver,
            nonce=request.nonce,
        )

        await db.commit()

        # Full reload: a partial refresh would expire the other
        # columns (updated_at is DB-computed by onupdate) and
        # serialize_message would then trigger an async lazy load.
        message = await message_repository.reload_with_relations(
            message.id
        )

        await manager.broadcast(
            message.conversation_id,
            {
                "event": "edit",
                "message_id": str(message.id),
                "sender_id": str(message.sender_id),
                "ciphertext": message.ciphertext,
                "encrypted_key_sender": message.encrypted_key_sender,
                "encrypted_key_receiver": message.encrypted_key_receiver,
                "nonce": message.nonce,
                "edited": True,
                "updated_at": message.updated_at.isoformat()
                if message.updated_at
                else None,
            },
        )

        return serialize_message(message)

    except ValueError as e:

        await db.rollback()

        raise HTTPException(
            status_code=400,
            detail=str(e),
        )


# ==========================================================
# TOGGLE EMOJI REACTION
#
# WhatsApp behaviour: tapping the same emoji again removes
# the reaction; a different emoji replaces it.
# ==========================================================

@router.put(
    "/{message_id}/reaction",
    dependencies=[
        rate_limit("messages.reaction", 60, 60),
    ],
)
async def toggle_reaction(
    message_id: UUID,
    request: ReactionRequest,
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

        result = await service.toggle_reaction(
            current_user=current_user,
            message_id=message_id,
            emoji=request.emoji,
        )

        await db.commit()

        message = await service.get_message(
            current_user,
            message_id,
        )

        await manager.broadcast(
            message.conversation_id,
            {
                "event": "reaction",
                **result,
            },
        )

        return result

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


# ==========================================================
# DELETE FOR EVERYONE
# ==========================================================

@router.delete(
    "/{message_id}",
    status_code=204,
    dependencies=[
        rate_limit("messages.delete", 30, 60),
    ],
)
async def delete_for_everyone(
    message_id: UUID,
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

        await service.delete_for_everyone(
            current_user=current_user,
            message_id=message_id,
        )

        await db.commit()

    except ValueError as e:

        await db.rollback()

        raise HTTPException(
            status_code=400,
            detail=str(e),
        )


# ==========================================================
# DELETE FOR ME
# ==========================================================

@router.delete(
    "/{message_id}/me",
    status_code=204,
    dependencies=[
        rate_limit("messages.delete", 30, 60),
    ],
)
async def delete_for_me(
    message_id: UUID,
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

        await service.delete_for_me(
            current_user=current_user,
            message_id=message_id,
        )

        await db.commit()

    except ValueError as e:

        await db.rollback()

        raise HTTPException(
            status_code=400,
            detail=str(e),
        )