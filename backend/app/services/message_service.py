import base64
from uuid import UUID

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
        encrypted_key: str,
        nonce: str,
        message_type: str = "text",
        reply_to_id: UUID | None = None,
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

        message = Message(
            conversation_id=conversation_id,
            sender_id=current_user.id,

            ciphertext=ciphertext,
            encrypted_key=encrypted_key,
            nonce=nonce,

            crypto_version=1,
            message_type=message_type,
            reply_to_id=reply_to_id,
        )

        return await self.message_repository.create_message(
            message
        )

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
            conversation_id
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