from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import and_

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

_UNSET = object()


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
    # Update Settings (pin / archive / mute)
    # ==========================================================

    async def update_settings(
        self,
        current_user: User,
        conversation_id: UUID,
        *,
        is_pinned: bool | None | object = _UNSET,
        is_archived: bool | None | object = _UNSET,
        muted_until: datetime | None | object = _UNSET,
        disappear_after_seconds: int | None | object = _UNSET,
    ) -> dict:

        settings = {
            "is_pinned": False,
            "is_archived": False,
            "muted": False,
            "disappear_after_seconds": None,
        }

        participant = (
            await self.conversation_repository.get_participant(
                conversation_id,
                current_user.id,
            )
        )

        if participant is None:
            raise PermissionError(
                "You are not a participant of this conversation."
            )

        if is_pinned is not _UNSET:
            participant.is_pinned = bool(is_pinned)

        if is_archived is not _UNSET:
            participant.is_archived = bool(is_archived)

        if muted_until is not _UNSET:
            participant.muted_until = muted_until

        # The disappearing-message timer is a property of the
        # conversation itself: any participant may change it and
        # everyone sees the same setting.
        if disappear_after_seconds is not _UNSET:

            conversation = (
                await self.conversation_repository.get_by_id(
                    conversation_id
                )
            )

            if conversation is None:
                raise PermissionError(
                    "Conversation not found."
                )

            conversation.disappear_after_seconds = (
                disappear_after_seconds
            )

            settings["disappear_after_seconds"] = (
                disappear_after_seconds
            )

        await self.conversation_repository.save()

        return {
            **settings,
            **self._participant_settings(participant),
        }

    # ==========================================================
    # Participant Settings Snapshot
    # ==========================================================

    def _participant_settings(self, participant) -> dict:

        # DB drivers may return naive datetimes (e.g. SQLite); normalize
        # to naive UTC so the comparison is always valid.
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        muted_until = participant.muted_until

        if muted_until is not None and muted_until.tzinfo is not None:
            muted_until = muted_until.astimezone(timezone.utc).replace(tzinfo=None)

        muted = muted_until is not None and muted_until > now

        return {
            "is_pinned": bool(participant.is_pinned),
            "is_archived": bool(participant.is_archived),
            "muted": muted,
        }

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
                    conversation.id,
                    current_user.id,
                )
            )

            unread_count = (
                await self.message_repository.count_unread(
                    conversation.id,
                    current_user.id,
                )
            )

            participant = (
                await self.conversation_repository.get_participant(
                    conversation.id,
                    current_user.id,
                )
            )

            settings = (
                self._participant_settings(participant)
                if participant
                else {
                    "is_pinned": False,
                    "is_archived": False,
                    "muted": False,
                }
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
                    "disappear_after_seconds":
                        conversation.disappear_after_seconds,
                    **settings,
                }
            )

        # Recency first, then pinned floats to the top (two stable
        # passes so pin order keeps inside each group).
        response.sort(
            key=lambda item: (
                item["updated_at"] or datetime.min.replace(tzinfo=timezone.utc)
            ),
            reverse=True,
        )

        response.sort(
            key=lambda item: not item["is_pinned"],
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