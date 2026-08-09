from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.session import get_db
from app.dependencies.auth import get_current_user
from app.dependencies.rate_limit import rate_limit

from app.models.user import User

from app.repositories.conversation_repository import (
    ConversationRepository,
)
from app.repositories.message_repository import (
    MessageRepository,
)

from app.schemas.conversation import (
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
# Open/Create Conversation
# ==========================================================

@router.post(
    "/private",
    response_model=ConversationResponse,
    dependencies=[
        rate_limit("conversations.create", 30, 60),
    ],
)
async def create_private_conversation(
    request: CreateConversationRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        conversation_repository = ConversationRepository(db)
        message_repository = MessageRepository(db)

        service = ConversationService(
            conversation_repository,
            message_repository,
        )

        
        conversation = await service.get_or_create_private_conversation(
            current_user,
            request.user_id,
        )

        
        await db.commit()

        
        await db.refresh(conversation)

        
        other_user = await conversation_repository.get_other_user(
            conversation.id,
            current_user.id,
        )

        
        
        last_message = await message_repository.get_last_message(
            conversation.id,
            current_user.id,
        )

        
        
        return {
            "id": conversation.id,
            "updated_at": conversation.updated_at,
            "other_user": other_user,
            "last_message": (
                {
                    "ciphertext": last_message.ciphertext,
                    "message_type": last_message.message_type,
                    "created_at": last_message.created_at,
                }
                if last_message
                else None
            ),
        }

    except Exception:
        traceback.print_exc()
        raise

# ==========================================================
# My Conversations
# ==========================================================

@router.get("/")
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
        current_user
    )