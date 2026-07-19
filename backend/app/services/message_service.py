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
    Business logic for messages.
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
        conversation_id: UUID,
        sender: User,
        content: str,
    ) -> Message:
        """
        Send a message in a conversation.
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

        if sender.id not in participant_ids:
            raise ValueError(
                "You are not a participant in this conversation."
            )

        message = Message(
            conversation_id=conversation_id,
            sender_id=sender.id,
            content=content,
            message_type="text",
        )

        return await self.message_repository.create_message(
            message
        )

    # ==========================================================
    # Get Messages
    # ==========================================================

    async def get_messages(
        self,
        conversation_id: UUID,
        current_user: User,
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
                "You are not a participant in this conversation."
            )

        return await self.message_repository.get_messages(
            conversation_id
        )