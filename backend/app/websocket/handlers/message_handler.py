from uuid import UUID

from app.models.user import User
from app.repositories.conversation_repository import (
    ConversationRepository,
)
from app.services.message_service import MessageService
from app.websocket.events import events


class MessageHandler:
    """
    Handles every message-related WebSocket event.

    Responsibilities:
    - Validate conversation access
    - Save messages
    - Broadcast messages

    It intentionally contains no WebSocket routing logic.
    """

    def __init__(
        self,
        conversation_repository: ConversationRepository,
        message_service: MessageService,
    ):
        self.conversation_repository = (
            conversation_repository
        )
        self.message_service = message_service

    # ==========================================================
    # Message
    # ==========================================================

    async def handle_message(
        self,
        current_user: User,
        conversation_id: UUID,
        content: str,
    ):
        """
        Save a message and broadcast it.
        """

        content = content.strip()

        if not content:
            return

        is_participant = (
            await self.conversation_repository.is_participant(
                conversation_id,
                current_user.id,
            )
        )

        if not is_participant:
            raise ValueError(
                "You are not a participant of this conversation."
            )

        message = (
            await self.message_service.send_message(
                current_user=current_user,
                conversation_id=conversation_id,
                content=content,
            )
        )

        await events.message(
            conversation_id,
            message,
        )

        return message