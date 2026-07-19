from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.repositories.conversation_repository import (
    ConversationRepository,
)
from app.schemas.conversation import (
    CreateConversationRequest,
    ConversationResponse,
)
from app.services.conversation_service import (
    ConversationService,
)

router = APIRouter(
    prefix="/conversations",
    tags=["Conversations"],
)


# ==========================================================
# Create or Open Conversation
# ==========================================================

@router.post(
    "/",
    response_model=ConversationResponse,
)
async def create_or_open_conversation(
    request: CreateConversationRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    repository = ConversationRepository(db)
    service = ConversationService(repository)

    conversation = (
        await service.get_or_create_private_conversation(
            current_user,
            request.user_id,
        )
    )

    return conversation


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
    repository = ConversationRepository(db)
    service = ConversationService(repository)

    return await service.my_conversations(
        current_user
    )