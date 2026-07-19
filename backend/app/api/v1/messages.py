from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.message_repository import MessageRepository
from app.schemas.message import (
    MessageResponse,
    SendMessageRequest,
)
from app.services.message_service import MessageService

router = APIRouter(
    prefix="/messages",
    tags=["Messages"],
)


# ==========================================================
# Send Message
# ==========================================================

@router.post(
    "/send",
    response_model=MessageResponse,
)
async def send_message(
    request: SendMessageRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    message_repository = MessageRepository(db)
    conversation_repository = ConversationRepository(db)

    service = MessageService(
        message_repository,
        conversation_repository,
    )

    try:
        return await service.send_message(
            current_user=current_user,
            conversation_id=request.conversation_id,
            content=request.content,
        )

    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=str(e),
        )


# ==========================================================
# Get Conversation Messages
# ==========================================================

@router.get(
    "/{conversation_id}",
    response_model=list[MessageResponse],
)
async def get_messages(
    conversation_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    message_repository = MessageRepository(db)
    conversation_repository = ConversationRepository(db)

    service = MessageService(
        message_repository,
        conversation_repository,
    )

    try:
        return await service.get_messages(
            current_user=current_user,
            conversation_id=conversation_id,
        )

    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=str(e),
        )