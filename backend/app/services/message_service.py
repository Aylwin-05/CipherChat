from uuid import UUID

from app.models.message import Message
from app.models.user import User
from app.repositories.conversation_repository import (
    ConversationRepository,
)
from app.repositories.message_repository import (
    MessageRepository,
)


class MessageService:
    """
    Business logic for sending and retrieving messages.
    """

    def __init__(
        self,
        message_repository: MessageRepository,
        conversation_repository: ConversationRepository,
    ):
        self.message_repository = message_repository
        self.conversation_repository = conversation_repository

    # ==========================================================
    # Send Message
    # ==========================================================

    async def send_message(
        self,
        current_user: User,
        conversation_id: UUID,
        content: str,
    ) -> Message:
        """
        Send a message to a conversation.
        """

        participants = (
            await self.conversation_repository.get_participants(
                conversation_id
            )
        )

        participant_ids = {
            participant.user_id
            for participant in participants
        }

        if current_user.id not in participant_ids:
            raise ValueError(
                "You are not a participant of this conversation."
            )

        message = Message(
            conversation_id=conversation_id,
            sender_id=current_user.id,
            content=content,
        )

        return await self.message_repository.create_message(
            message
        )

    # ==========================================================
    # Get Conversation Messages
    # ==========================================================

    async def get_messages(
        self,
        current_user: User,
        conversation_id: UUID,
    ):
        """
        Return all messages from a conversation.
        """

        participants = (
            await self.conversation_repository.get_participants(
                conversation_id
            )
        )

        participant_ids = {
            participant.user_id
            for participant in participants
        }

        if current_user.id not in participant_ids:
            raise ValueError(
                "You are not allowed to view this conversation."
            )

        return await self.message_repository.get_messages(
            conversation_id
        )