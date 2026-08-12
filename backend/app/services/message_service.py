from uuid import UUID

from datetime import timedelta
from datetime import datetime, timezone

from fastapi import UploadFile

from app.models.message import Message
from app.models.user import User
from app.repositories.conversation_repository import (
    ConversationRepository,
)
from app.repositories.message_repository import (
    MessageRepository,
)
from app.services.attachment_service import (
    AttachmentService,
)


class MessageService:
    """
    End-to-End Encrypted Message Service.

    The backend NEVER encrypts or decrypts messages.

    Responsibilities:

    • Validate conversation membership
    • Decode Base64 payloads
    • Store encrypted payloads
    • Manage metadata
    """

    def __init__(
        self,
        message_repository: MessageRepository,
        conversation_repository: ConversationRepository,
        attachment_service: AttachmentService,
    ):
        self.message_repository = message_repository
        self.conversation_repository = conversation_repository
        self.attachment_service = attachment_service

    # ==========================================================
    # INTERNAL
    # ==========================================================

    async def _validate_participant(
        self,
        current_user: User,
        conversation_id: UUID,
    ):

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

    # ==========================================================
    # SEND ENCRYPTED MESSAGE
    # ==========================================================

    async def send_message(
        self,
        current_user: User,
        conversation_id: UUID,
        ciphertext: str,
        encrypted_key_sender: str,
        encrypted_key_receiver: str,
        nonce: str,
        message_type: str = "text",
        reply_to_id: UUID | None = None,
        is_forwarded: bool = False,
        attachment_ids: list[UUID] | None = None,
    ) -> Message:

        await self._validate_participant(
            current_user,
            conversation_id,
        )

        if reply_to_id:

            reply = (
                await self.message_repository.get_reply_message(
                    reply_to_id
                )
            )

            if reply is None:
                raise ValueError(
                    "Reply target does not exist."
                )

        expires_at = None

        conversation = (
            await self.conversation_repository.get_by_id(
                conversation_id
            )
        )

        if conversation and conversation.disappear_after_seconds:

            expires_at = (
                datetime.now(timezone.utc)
                + timedelta(
                    seconds=conversation.disappear_after_seconds
                )
            )

        message = Message(
            conversation_id=conversation_id,
            sender_id=current_user.id,

            ciphertext=ciphertext,

            encrypted_key_sender=encrypted_key_sender,

            encrypted_key_receiver=encrypted_key_receiver,

            nonce=nonce,

            crypto_version=1,

            message_type=message_type,

            reply_to_id=reply_to_id,

            is_forwarded=is_forwarded,

            expires_at=expires_at,
        )

        message = await self.message_repository.create_message(
            message
        )

        # Attach uploaded files to this message
        if attachment_ids:

            for attachment_id in attachment_ids:

                attachment = await self.attachment_service.get_attachment(
                    attachment_id
                )

                if attachment:

                    attachment.message_id = message.id

        return message

    # ==========================================================
    # GET MESSAGES
    # ==========================================================

    async def get_messages(
        self,
        current_user: User,
        conversation_id: UUID,
    ):

        await self._validate_participant(
            current_user,
            conversation_id,
        )

        return await self.message_repository.get_conversation_messages(
            conversation_id,
            current_user.id,
        )

    # ==========================================================
    # GET SINGLE MESSAGE
    # ==========================================================

    async def get_message(
        self,
        current_user: User,
        message_id: UUID,
    ):

        message = await self.message_repository.get_by_id(
            message_id
        )

        if message is None:
            raise ValueError(
                "Message not found."
            )

        await self._validate_participant(
            current_user,
            message.conversation_id,
        )

        return message

    # ==========================================================
    # MARK READ
    # ==========================================================

    async def mark_read(
        self,
        current_user: User,
        message_id: UUID,
    ):

        message = await self.get_message(
            current_user,
            message_id,
        )

        return await self.message_repository.mark_read(
            message
        )

    # ==========================================================
    # EDIT MESSAGE
    # ==========================================================

    async def edit_message(
        self,
        current_user: User,
        message_id: UUID,
        ciphertext: str,
        encrypted_key_sender: str,
        encrypted_key_receiver: str,
        nonce: str,
    ) -> Message:

        message = await self.get_message(
            current_user,
            message_id,
        )

        if message.sender_id != current_user.id:
            raise ValueError(
                "Only sender can edit message."
            )

        if message.deleted_for_everyone:
            raise ValueError(
                "Message has already been deleted."
            )

        return await self.message_repository.edit_payload(
            message,
            ciphertext,
            encrypted_key_sender,
            encrypted_key_receiver,
            nonce,
        )

    # ==========================================================
    # REACTIONS
    # ==========================================================

    async def toggle_reaction(
        self,
        current_user: User,
        message_id: UUID,
        emoji: str,
    ) -> dict:
        """
        WhatsApp-style toggle:
        - same emoji again  -> reaction removed
        - different emoji   -> reaction replaced
        - new emoji         -> reaction added
        """

        message = await self.get_message(
            current_user,
            message_id,
        )

        existing = await self.message_repository.get_reaction(
            message_id,
            current_user.id,
        )

        action = "add"
        created_at = None

        if existing is not None and existing.emoji == emoji:

            await self.message_repository.remove_reaction(
                existing
            )

            action = "remove"

        else:

            if existing is not None:

                await self.message_repository.remove_reaction(
                    existing
                )

            reaction = await self.message_repository.add_reaction(
                message_id,
                current_user.id,
                emoji,
            )

            created_at = reaction.created_at

        return {
            "message_id": str(message.id),
            "user_id": str(current_user.id),
            "emoji": emoji,
            "action": action,
            "created_at": (
                created_at.isoformat()
                if created_at is not None
                else None
            ),
        }

    # ==========================================================
    # DELETE
    # ==========================================================

    async def delete_for_everyone(
        self,
        current_user: User,
        message_id: UUID,
    ):

        message = await self.get_message(
            current_user,
            message_id,
        )

        if message.sender_id != current_user.id:
            raise ValueError(
                "Only sender can delete message."
            )

        return await self.message_repository.delete_for_everyone(
            message
        )

    # ==========================================================
    # DELETE FOR ME
    # ==========================================================

    async def delete_for_me(
        self,
        current_user: User,
        message_id: UUID,
    ):

        message = await self.get_message(
            current_user,
            message_id,
        )

        return await self.message_repository.delete_for_me(
            message,
            current_user.id,
        )