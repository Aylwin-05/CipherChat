from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db
from app.dependencies.auth import get_current_user
from app.models.user import User

from app.repositories.conversation_repository import (
    ConversationRepository,
)
from app.repositories.message_repository import (
    MessageRepository,
)

from app.schemas.conversation import (
    ConversationCreateResponse,
    ConversationResponse,
    CreateConversationRequest,
)

from app.services.conversation_service import (
    ConversationService,
)

router = APIRouter(
    prefix="/conversations",
    tags=["Conversations"],
)


# ==========================================================
# Open/Create Private Conversation
# ==========================================================

@router.post(
    "/private",
    response_model=ConversationCreateResponse,
)
async def create_private_conversation(
    request: CreateConversationRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    conversation_repository = ConversationRepository(db)

    message_repository = MessageRepository(db)

    service = ConversationService(
        conversation_repository,
        message_repository,
    )

    return await service.get_or_create_private_conversation(
        current_user=current_user,
        other_user_id=request.user_id,
    )


# ==========================================================
# My Conversations
# ==========================================================

@router.get(
    "/",
    response_model=list[ConversationResponse],
)
async def my_conversations(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    conversation_repository = ConversationRepository(db)

    message_repository = MessageRepository(db)

    service = ConversationService(
        conversation_repository,
        message_repository,
    )

    return await service.my_conversations(
        current_user=current_user,
    )