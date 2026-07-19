from uuid import UUID

from app.models.conversation import Conversation
from app.models.conversation_participant import (
    ConversationParticipant,
)
from app.models.user import User
from app.repositories.conversation_repository import (
    ConversationRepository,
)


class ConversationService:
    """
    Business logic for conversations.
    """

    def __init__(
        self,
        repository: ConversationRepository,
    ):
        self.repository = repository

    # ==========================================================
    # Get or Create Private Conversation
    # ==========================================================

    async def get_or_create_private_conversation(
        self,
        current_user: User,
        other_user_id: UUID,
    ) -> Conversation:
        """
        Returns an existing private conversation
        or creates a new one.
        """

        conversation = (
            await self.repository.get_private_conversation(
                current_user.id,
                other_user_id,
            )
        )

        if conversation:
            return conversation

        conversation = Conversation()

        conversation = (
            await self.repository.create_conversation(
                conversation
            )
        )

        participant1 = ConversationParticipant(
            conversation_id=conversation.id,
            user_id=current_user.id,
        )

        participant2 = ConversationParticipant(
            conversation_id=conversation.id,
            user_id=other_user_id,
        )

        await self.repository.add_participant(
            participant1
        )

        await self.repository.add_participant(
            participant2
        )

        return conversation

    # ==========================================================
    # Get My Conversations
    # ==========================================================

    async def my_conversations(
        self,
        current_user: User,
    ):
        return await self.repository.get_user_conversations(
            current_user.id
        )

    # ==========================================================
    # Get Participants
    # ==========================================================

    async def participants(
        self,
        conversation_id: UUID,
    ):
        return await self.repository.get_participants(
            conversation_id
        )