from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

import logging

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

logger = logging.getLogger("app.services.conversation_service")

_UNSET = object()


class ConversationService:
    """
    Business logic for conversations.
    """

    def __init__(
        self,
        conversation_repository: ConversationRepository,
        message_repository: MessageRepository,
        friend_repository=None,
    ):
        self.conversation_repository = conversation_repository
        self.message_repository = message_repository
        self.friend_repository = friend_repository

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
    # GROUP CHATS
    # ==========================================================

    # ----------------------------------------------------------
    # Notification helper: every member's sidebar refreshes.
    # ----------------------------------------------------------

    async def _notify_members(
        self,
        member_ids,
        event: str,
        payload: dict | None = None,
    ):
        message = {
            "event": event,
            **(payload or {}),
        }

        for member_id in member_ids:
            await manager.send_to_user(member_id, message)

    # ----------------------------------------------------------
    # Create Group
    # ----------------------------------------------------------

    async def create_group(
        self,
        current_user: User,
        name: str,
        member_ids: list[UUID],
    ) -> Conversation:

        name = (name or "").strip()

        if not name:
            raise ValueError("Group name cannot be empty.")

        if len(name) > 100:
            raise ValueError(
                "Group name must be 100 characters or fewer."
            )

        if len(member_ids) < 1:
            raise ValueError(
                "A group needs at least one member."
            )

        if len(member_ids) > 49:
            raise ValueError(
                "A group can have at most 50 members."
            )

        member_ids = list(dict.fromkeys(member_ids))

        if current_user.id in member_ids:
            raise ValueError(
                "You cannot add yourself as a member."
            )

        await self._validate_members_are_friends(
            current_user.id,
            member_ids,
        )

        try:

            conversation = Conversation(
                name=name,
                conversation_type="group",
            )

            conversation = (
                await self.conversation_repository.create_conversation(
                    conversation
                )
            )

            creator = ConversationParticipant(
                conversation_id=conversation.id,
                user_id=current_user.id,
                is_admin=True,
            )

            await self.conversation_repository.add_participant(
                creator
            )

            member_ids = [
                user_id
                for user_id in member_ids
                if user_id != current_user.id
            ]

            for user_id in member_ids:

                participant = ConversationParticipant(
                    conversation_id=conversation.id,
                    user_id=user_id,
                )

                await self.conversation_repository.add_participant(
                    participant
                )

            await self.conversation_repository.commit()

        except Exception:
            await self.conversation_repository.rollback()
            raise

        await self._notify_members(
            member_ids,
            "conversations_changed",
        )

        return conversation

    # ----------------------------------------------------------
    # Validate members are friends of the acting user
    # ----------------------------------------------------------

    async def _validate_members_are_friends(
        self,
        actor_id: UUID,
        member_ids: list[UUID],
    ):

        if self.friend_repository is None:
            return

        for member_id in member_ids:

            friendship = (
                await self.friend_repository.get_existing_friendship(
                    actor_id,
                    member_id,
                )
            )

            if friendship is None:
                raise ValueError(
                    "All group members must be your friends."
                )

    # ----------------------------------------------------------
    # Group Detail
    # ----------------------------------------------------------

    async def get_group_detail(
        self,
        current_user: User,
        conversation_id: UUID,
    ) -> dict:

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

        conversation = (
            await self.conversation_repository.get_by_id(
                conversation_id
            )
        )

        if conversation is None:
            raise PermissionError(
                "Conversation not found."
            )

        if conversation.conversation_type != "group":
            raise ValueError(
                "This is not a group conversation."
            )

        rows = (
            await self.conversation_repository.get_participants_with_users(
                conversation_id
            )
        )

        participants = []

        for row in rows:

            row_participant, row_user, public_key = row

            participants.append(
                {
                    "user_id": row_user.id,
                    "display_name": row_user.display_name,
                    "username": row_user.username,
                    "avatar_url": row_user.avatar_url,
                    "online_status": (
                        "online"
                        if manager.is_online(row_user.id)
                        else "offline"
                    ),
                    "public_key": public_key,
                    "is_admin": bool(row_participant.is_admin),
                    "joined_at": row_participant.joined_at,
                }
            )

        return {
            "id": conversation.id,
            "name": conversation.name,
            "conversation_type": conversation.conversation_type,
            "created_at": conversation.created_at,
            "participant_count": len(participants),
            "participants": participants,
            "is_admin": bool(participant.is_admin),
        }

    # ----------------------------------------------------------
    # Add Members (admin only)
    # ----------------------------------------------------------

    async def add_group_members(
        self,
        current_user: User,
        conversation_id: UUID,
        member_ids: list[UUID],
    ) -> dict:

        member_ids = list(dict.fromkeys(member_ids))

        if not member_ids:
            raise ValueError(
                "No members to add."
            )

        if current_user.id in member_ids:
            raise ValueError(
                "You cannot add yourself as a member."
            )

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

        conversation = (
            await self.conversation_repository.get_by_id(
                conversation_id
            )
        )

        if conversation is None:
            raise PermissionError(
                "Conversation not found."
            )

        if conversation.conversation_type != "group":
            raise ValueError(
                "This is not a group conversation."
            )

        if not participant.is_admin:
            raise PermissionError(
                "Only group admins can add members."
            )

        await self._validate_members_are_friends(
            current_user.id,
            member_ids,
        )

        existing_ids = {
            row_participant.user_id
            for row_participant
            in await self.conversation_repository.get_participants(
                conversation_id
            )
        }

        added_ids = []

        for user_id in member_ids:

            if user_id in existing_ids:
                continue

            new_participant = ConversationParticipant(
                conversation_id=conversation_id,
                user_id=user_id,
            )

            await self.conversation_repository.add_participant(
                new_participant
            )

            added_ids.append(user_id)

        await self.conversation_repository.commit()

        await self._notify_members(
            added_ids,
            "conversations_changed",
        )

        return {
            "conversation_id": str(conversation_id),
            "added_members": [
                str(user_id)
                for user_id in added_ids
            ],
            "participant_count": len(existing_ids) + len(added_ids),
        }

    # ----------------------------------------------------------
    # Leave Group
    # ----------------------------------------------------------

    async def leave_group(
        self,
        current_user: User,
        conversation_id: UUID,
    ) -> dict:

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

        conversation = (
            await self.conversation_repository.get_by_id(
                conversation_id
            )
        )

        if conversation is None:
            raise PermissionError(
                "Conversation not found."
            )

        if conversation.conversation_type != "group":
            raise ValueError(
                "This is not a group conversation."
            )

        rows = (
            await self.conversation_repository.get_participants_with_users(
                conversation_id
            )
        )

        # Who remains after the leaver is removed?
        remaining = [
            (row_participant, row_user, _public_key)
            for row_participant, row_user, _public_key in rows
            if row_participant.user_id != current_user.id
        ]

        if not remaining:

            # Last member left: the group ceases to exist.
            await self.conversation_repository.remove_participant(
                conversation_id,
                current_user.id,
            )

            await self.conversation_repository.delete_conversation_record(
                conversation_id
            )

            await self.conversation_repository.commit()

            return {
                "conversation_id": str(conversation_id),
                "status": "deleted",
            }

        # If the leaver was the only admin, promote the most
        # recently added remaining member so the group keeps
        # at least one admin (WhatsApp promotes whoever was
        # added first; we promote the earliest joiner).
        if participant.is_admin:

            admins = [
                row_participant
                for row_participant, _row_user, _pk in remaining
                if row_participant.is_admin
            ]

            if not admins:

                earliest = min(
                    remaining,
                    key=lambda item: item[0].joined_at
                    or datetime.min.replace(tzinfo=timezone.utc),
                )[0]

                earliest.is_admin = True

        await self.conversation_repository.remove_participant(
            conversation_id,
            current_user.id,
        )

        await self.conversation_repository.commit()

        await self._notify_members(
            [
                row_user.id
                for _row_participant, row_user, _pk in remaining
            ],
            "conversations_changed",
        )

        return {
            "conversation_id": str(conversation_id),
            "status": "left",
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

            is_group = (
                conversation.conversation_type == "group"
            )

            other_user = None

            participant_count = None

            if is_group:

                participant_count = (
                    await self.conversation_repository.get_participant_count(
                        conversation.id
                    )
                )

            else:

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
                    "conversation_type": conversation.conversation_type,
                    "name": conversation.name if is_group else None,
                    "participant_count": participant_count,
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
                    "delete_requested_by":
                        str(conversation.delete_requested_by)
                        if conversation.delete_requested_by
                        else None,
                    "delete_requested_at":
                        conversation.delete_requested_at.isoformat()
                        if conversation.delete_requested_at
                        else None,
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
    # TWO-PARTY CONVERSATION DELETION
    #
    # User 1 presses "delete chat": nothing is erased yet, the
    # other participant is notified in real time and asked to
    # confirm. Only when BOTH users consent is every message,
    # attachment (rows AND physical files) and the conversation
    # itself purged from the server.
    # ==========================================================

    def _delete_state(
        self,
        conversation_id: UUID,
        status: str,
        conversation: Conversation | None = None,
    ) -> dict:

        return {
            "conversation_id": str(conversation_id),
            "status": status,
            "delete_requested_by": (
                str(conversation.delete_requested_by)
                if conversation
                and conversation.delete_requested_by
                else None
            ),
            "delete_requested_at": (
                conversation.delete_requested_at.isoformat()
                if conversation
                and conversation.delete_requested_at
                else None
            ),
        }

    async def _verify_delete_access(
        self,
        conversation_id: UUID,
        current_user: User,
    ) -> Conversation:

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

        conversation = (
            await self.conversation_repository.get_by_id(
                conversation_id
            )
        )

        if conversation is None:
            raise PermissionError(
                "Conversation not found."
            )

        if conversation.conversation_type == "group":
            raise ValueError(
                "Conversation deletion is only available "
                "for private chats."
            )

        return conversation

    async def _perform_full_delete(
        self,
        conversation: Conversation,
    ):
        """
        Both participants consented: purge everything.

        1. Capture participant ids BEFORE the wipe (the manager
           resolves members from the DB, and after deletion the
           conversation no longer exists).
        2. Unlink attachment files from disk.
        3. Delete rows (reactions, keys, attachments, sessions,
           messages, participants, conversation) + commit.
        4. Broadcast `conversation_deleted` to every participant.
        """

        participants = (
            await self.conversation_repository.get_participants(
                conversation.id
            )
        )

        member_ids = [
            participant.user_id
            for participant in participants
        ]

        attachments = (
            await self.message_repository.get_conversation_attachments(
                conversation.id
            )
        )

        storage_paths = [
            attachment.storage_path
            for attachment in attachments
            if attachment.storage_path
        ]

        await self.message_repository.delete_conversation_content(
            conversation.id
        )

        await self.conversation_repository.delete_conversation_record(
            conversation.id
        )

        await self.conversation_repository.commit()

        # Physical files are outside the DB transaction: unlink
        # best-effort so one locked file never blocks the purge.
        for storage_path in storage_paths:

            try:

                path = Path(storage_path)

                if path.exists():
                    path.unlink()

            except OSError as error:

                logger.warning(
                    "Could not unlink attachment file %s: %s",
                    storage_path,
                    error,
                )

        payload = {
            "event": "conversation_deleted",
            "conversation_id": str(conversation.id),
        }

        for member_id in member_ids:
            await manager.send_to_user(member_id, payload)

    # ----------------------------------------------------------
    # Request deletion (User 1)
    # ----------------------------------------------------------

    async def request_conversation_delete(
        self,
        current_user: User,
        conversation_id: UUID,
    ) -> dict:

        conversation = await self._verify_delete_access(
            conversation_id,
            current_user,
        )

        # The other participant already requested: this call is
        # their confirmation — wipe now.
        if (
            conversation.delete_requested_by is not None
            and conversation.delete_requested_by
            != current_user.id
        ):

            await self._perform_full_delete(conversation)

            return self._delete_state(
                conversation_id,
                "deleted",
            )

        if conversation.delete_requested_by is None:

            conversation.delete_requested_by = current_user.id

            conversation.delete_requested_at = datetime.now(
                timezone.utc
            )

            await self.conversation_repository.save()

            await self.conversation_repository.commit()

            # Real-time popup for the other participant.
            await manager.broadcast(
                conversation_id,
                {
                    "event": "conversation_delete_request",
                    "conversation_id": str(conversation_id),
                    "requested_by": str(current_user.id),
                    "requested_by_name":
                        current_user.display_name,
                    "requested_at": conversation
                        .delete_requested_at.isoformat(),
                },
            )

        return self._delete_state(
            conversation_id,
            "requested",
            conversation,
        )

    # ----------------------------------------------------------
    # Confirm deletion (User 2)
    # ----------------------------------------------------------

    async def confirm_conversation_delete(
        self,
        current_user: User,
        conversation_id: UUID,
    ) -> dict:

        conversation = await self._verify_delete_access(
            conversation_id,
            current_user,
        )

        if conversation.delete_requested_by is None:

            raise ValueError(
                "No pending deletion request for this conversation."
            )

        if conversation.delete_requested_by == current_user.id:

            raise ValueError(
                "You already requested this deletion; "
                "waiting for the other participant."
            )

        # The other participant requested and we just confirmed:
        # both consented -> wipe everything.
        await self._perform_full_delete(conversation)

        return self._delete_state(
            conversation_id,
            "deleted",
        )

    # ----------------------------------------------------------
    # Cancel deletion (requester, or the other user's "Not now")
    # ----------------------------------------------------------

    async def cancel_conversation_delete(
        self,
        current_user: User,
        conversation_id: UUID,
    ) -> dict:

        conversation = await self._verify_delete_access(
            conversation_id,
            current_user,
        )

        if conversation.delete_requested_by is None:

            raise ValueError(
                "No pending deletion request for this conversation."
            )

        conversation.delete_requested_by = None

        conversation.delete_requested_at = None

        await self.conversation_repository.save()

        await self.conversation_repository.commit()

        await manager.broadcast(
            conversation_id,
            {
                "event": "conversation_delete_cancelled",
                "conversation_id": str(conversation_id),
                "cancelled_by": str(current_user.id),
            },
        )

        return self._delete_state(
            conversation_id,
            "cancelled",
            conversation,
        )

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