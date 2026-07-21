from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select

from app.models.message import Message
from app.repositories.base_repository import BaseRepository


class MessageRepository(BaseRepository):
    """
    Repository for all message operations.
    """

    # ==========================================================
    # Create Message
    # ==========================================================

    async def create_message(
        self,
        message: Message,
    ) -> Message:
        return await self.create(message)

    # ==========================================================
    # Get Conversation Messages
    # ==========================================================

    async def get_messages(
        self,
        conversation_id: UUID,
    ):

        result = await self.execute(
            select(Message)
            .where(
                Message.conversation_id == conversation_id
            )
            .order_by(
                Message.created_at.asc()
            )
        )

        return result.scalars().all()

    # ==========================================================
    # Get Last Message
    # ==========================================================

    async def get_last_message(
        self,
        conversation_id: UUID,
    ) -> Message | None:

        result = await self.execute(
            select(Message)
            .where(
                Message.conversation_id == conversation_id
            )
            .order_by(
                Message.created_at.desc()
            )
            .limit(1)
        )

        return result.scalar_one_or_none()

    # ==========================================================
    # Get Message By ID
    # ==========================================================

    async def get_by_id(
        self,
        message_id: UUID,
    ) -> Message | None:

        result = await self.execute(
            select(Message).where(
                Message.id == message_id
            )
        )

        return result.scalar_one_or_none()

    # ==========================================================
    # Mark Delivered
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
    # Mark Read
    # ==========================================================

    async def mark_read(
        self,
        message: Message,
    ):

        message.is_read = True

        if message.read_at is None:

            message.read_at = datetime.now(
                timezone.utc
            )

        if message.delivered_at is None:

            message.delivered_at = datetime.now(
                timezone.utc
            )

        await self.update()