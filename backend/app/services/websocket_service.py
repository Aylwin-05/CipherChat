from uuid import UUID

from app.models.message import Message
from app.models.user import User
from app.repositories.conversation_repository import (
    ConversationRepository,
)
from app.repositories.message_repository import (
    MessageRepository,
)
from app.services.message_service import MessageService
from app.websocket.events import events


class WebSocketService:
    """
    Handles websocket business operations.

    Responsibilities:
    - Verify conversation access
    - Store messages
    - Broadcast messages
    """

    def __init__(
        self,
        conversation_repository: ConversationRepository,
        message_repository: MessageRepository,
    ):
        self.conversation_repository = conversation_repository
        self.message_repository = message_repository

        self.message_service = MessageService(
            message_repository,
            conversation_repository,
        )

    # ==========================================================
    # Verify Conversation Access
    # ==========================================================

    async def verify_conversation_access(
        self,
        conversation_id: UUID,
        current_user: User,
    ) -> bool:

        participants = (
            await self.conversation_repository.get_participants(
                conversation_id
            )
        )

        participant_ids = {
            participant.user_id
            for participant in participants
        }

        return current_user.id in participant_ids

    # ==========================================================
    # Handle Message
    # ==========================================================

    async def handle_message(
        self,
        conversation_id: UUID,
        current_user: User,
        content: str,
    ) -> Message:

        message = await self.message_service.send_message(
            conversation_id=conversation_id,
            sender=current_user,
            content=content,
        )

        # Broadcast using the unified event system
        await events.message(
            conversation_id,
            message,
        )

        return message