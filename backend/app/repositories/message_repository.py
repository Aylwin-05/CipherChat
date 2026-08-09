from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.models.message import Message
from app.repositories.base_repository import BaseRepository


class MessageRepository(BaseRepository):
    """
    Repository responsible for encrypted messages.

    IMPORTANT

    The repository NEVER knows plaintext.

    It only stores:

    • ciphertext
    • encrypted AES key
    • nonce
    • metadata
    """

    # ==========================================================
    # CREATE
    # ==========================================================

    async def create_message(
        self,
        message: Message,
    ) -> Message:

        return await self.create(message)

    # ==========================================================
    # GET
    # ==========================================================

    async def get_by_id(
        self,
        message_id: UUID,
    ) -> Message | None:

        result = await self.execute(

            select(Message)
            .options(
                selectinload(Message.attachments)
            )
            .where(
                Message.id == message_id
            )

        )

        return result.scalar_one_or_none()

    # ==========================================================
    # GET CONVERSATION
    # ==========================================================

    async def get_conversation_messages(
        self,
        conversation_id: UUID,
        user_id: UUID | None = None,
    ) -> list[Message]:

        result = await self.execute(

            select(Message)
            .options(
                selectinload(Message.attachments)
            )
            .where(
                Message.conversation_id == conversation_id
            )
            .order_by(
                Message.created_at.asc()
            )

        )

        messages = result.scalars().all()

        # "Delete for me": hide messages the user removed
        if user_id is not None:

            messages = [
                message
                for message in messages
                if str(user_id)
                not in (message.deleted_for or [])
            ]

        return messages

    # ==========================================================
    # LAST MESSAGE
    # ==========================================================

    async def get_last_message(
        self,
        conversation_id: UUID,
        user_id: UUID | None = None,
    ) -> Message | None:

        result = await self.execute(

            select(Message)
            .options(
                selectinload(Message.attachments)
            )
            .where(
                Message.conversation_id == conversation_id
            )
            .order_by(
                Message.created_at.desc()
            )
            .limit(200)

        )

        messages = result.scalars().all()

        # "Delete for me": hide messages the user removed
        if user_id is not None:

            messages = [
                message
                for message in messages
                if str(user_id)
                not in (message.deleted_for or [])
            ]

        return messages[0] if messages else None

    # ==========================================================
    # DELIVERY
    # ==========================================================

    async def mark_delivered(
        self,
        message: Message,
    ):

        if message.delivered_at is None:

            message.delivered_at = datetime.now(
                timezone.utc
            )

            await self.update()

    # ==========================================================
    # READ
    # ==========================================================

    async def mark_read(
        self,
        message: Message,
    ):

        message.is_read = True

        if message.delivered_at is None:

            message.delivered_at = datetime.now(
                timezone.utc
            )

        if message.read_at is None:

            message.read_at = datetime.now(
                timezone.utc
            )

        await self.update()

    # ==========================================================
    # UNREAD COUNT
    # ==========================================================

    async def count_unread(
        self,
        conversation_id: UUID,
        user_id: UUID,
    ) -> int:
        """Count messages sent by others that the user hasn't read."""

        result = await self.db.execute(
            select(Message.id)
            .where(
                Message.conversation_id == conversation_id,
                Message.sender_id != user_id,
                Message.is_read.is_(False),
            )
        )

        return len(result.all())

    # ==========================================================
    # DELETE
    # ==========================================================

    async def delete_for_everyone(
        self,
        message: Message,
    ) -> Message:

        message.deleted_for_everyone = True

        await self.update()

        return message

    async def delete_for_me(
        self,
        message: Message,
        user_id: UUID,
    ) -> Message:

        user_id = str(user_id)

        if user_id not in message.deleted_for:

            message.deleted_for.append(user_id)

            await self.update()

        return message

    # ==========================================================
    # REPLY
    # ==========================================================

    async def get_reply_message(
        self,
        reply_to_id: UUID,
    ) -> Message | None:

        result = await self.execute(

            select(Message).where(
                Message.id == reply_to_id
            )

        )

        return result.scalar_one_or_none()

    # ==========================================================
    # SAVE
    # ==========================================================

    async def save(
        self,
        message: Message,
    ) -> Message:

        await self.update()

        return message