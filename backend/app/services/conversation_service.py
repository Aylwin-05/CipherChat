from uuid import UUID

from app.models.conversation import Conversation
from app.models.conversation_participant import (
    ConversationParticipant,
)
from app.models.user import User

from app.repositories.conversation_repository import (
    ConversationRepository,
)
from app.repositories.message_repository import (
    MessageRepository,
)

from app.websocket.connection_manager import manager


class ConversationService:
    """
    Business logic for conversations.
    """

    def __init__(
        self,
        conversation_repository: ConversationRepository,
        message_repository: MessageRepository,
    ):
        self.conversation_repository = conversation_repository
        self.message_repository = message_repository

    # ==========================================================
    # Get or Create Private Conversation
    # ==========================================================

    async def get_or_create_private_conversation(
        self,
        current_user: User,
        other_user_id: UUID,
    ) -> Conversation:

        conversation = (
            await self.conversation_repository.get_private_conversation(
                current_user.id,
                other_user_id,
            )
        )

        if conversation:
            return conversation

        try:

            conversation = Conversation()

            conversation = (
                await self.conversation_repository.create_conversation(
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

            await self.conversation_repository.add_participant(
                participant1
            )

            await self.conversation_repository.add_participant(
                participant2
            )

            # --------------------------------------
            # SAVE EVERYTHING
            # --------------------------------------

            await self.conversation_repository.commit()

            return conversation

        except Exception:

            await self.conversation_repository.rollback()

            raise

    # ==========================================================
    # My Conversations
    # ==========================================================

    async def my_conversations(
        self,
        current_user: User,
    ):

        conversations = (
            await self.conversation_repository.get_user_conversations(
                current_user.id
            )
        )

        response = []

        for conversation in conversations:

            other_user = (
                await self.conversation_repository.get_other_user(
                    conversation.id,
                    current_user.id,
                )
            )

            if other_user is None:
                continue

            other_user.online_status = (
                "online"
                if manager.is_online(other_user.id)
                else "offline"
            )

            last_message = (
                await self.message_repository.get_last_message(
                    conversation.id
                )
            )

            unread_count = (
                await self.message_repository.count_unread(
                    conversation.id,
                    current_user.id,
                )
            )

            response.append(
                {
                    "id": conversation.id,
                    "updated_at": conversation.updated_at,
                    "other_user": other_user,
                    "last_message": (
                        {
                            "ciphertext": last_message.ciphertext,
                            "created_at": last_message.created_at,
                            "message_type": last_message.message_type,
                        }
                        if last_message
                        else None
                    ),
                    "unread_count": unread_count,
                }
            )

        return response

    # ==========================================================
    # Participants
    # ==========================================================

    async def participants(
        self,
        conversation_id: UUID,
    ):
        return await self.conversation_repository.get_participants(
            conversation_id
        )