from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.repositories.conversation_repository import (
    ConversationRepository,
)
from app.repositories.message_repository import (
    MessageRepository,
)
from app.services.message_service import MessageService


class WebSocketService:
    """
    Business logic for WebSocket events.
    """

    def __init__(
        self,
        db: AsyncSession,
    ):
        self.message_service = MessageService(
            message_repository=MessageRepository(db),
            conversation_repository=ConversationRepository(
                db
            ),
        )

    # ==========================================================
    # Save Chat Message
    # ==========================================================

    async def save_message(
        self,
        current_user: User,
        conversation_id: UUID,
        content: str,
    ):
        """
        Save a chat message.
        """

        return await self.message_service.send_message(
            current_user=current_user,
            conversation_id=conversation_id,
            content=content,
        )