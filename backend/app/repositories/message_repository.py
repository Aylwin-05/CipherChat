from uuid import UUID

from sqlalchemy import select

from app.models.message import Message
from app.repositories.base_repository import BaseRepository


class MessageRepository(BaseRepository):
    """
    Repository for message operations.
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
            .order_by(Message.created_at.asc())
        )

        return result.scalars().all()

    # ==========================================================
    # Mark Read
    # ==========================================================

    async def mark_read(
        self,
        message: Message,
    ):
        message.is_read = True
        await self.update()

    # ==========================================================
    # Get Message
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