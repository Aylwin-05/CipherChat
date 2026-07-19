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
from app.websocket.manager import manager


class WebSocketService:
    """
    Handles websocket business logic.
    """

    def __init__(
        self,
        conversation_repository: ConversationRepository,
        message_repository: MessageRepository,
    ):
        self.conversation_repository = conversation_repository
        self.message_repository = message_repository

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
    # Handle Incoming Message
    # ==========================================================

    async def handle_message(
        self,
        conversation_id: UUID,
        sender: User,
        content: str,
    ) -> Message:

        message_service = MessageService(
            self.message_repository,
            self.conversation_repository,
        )

        message = await message_service.send_message(
            conversation_id=conversation_id,
            sender=sender,
            content=content,
        )

        await manager.broadcast(
            conversation_id,
            {
                "event": "message",
                "data": {
                    "id": str(message.id),
                    "conversation_id": str(message.conversation_id),
                    "sender_id": str(message.sender_id),
                    "content": message.content,
                    "message_type": message.message_type,
                    "created_at": message.created_at.isoformat(),
                },
            },
        )

        return message