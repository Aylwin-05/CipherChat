from uuid import UUID

from app.models.attachment import Attachment
from app.repositories.base_repository import BaseRepository
from sqlalchemy import select


class AttachmentRepository(BaseRepository):

    """
    Repository for Attachment CRUD operations.
    """

    # ==========================================================
    # Create
    # ==========================================================

    async def create_attachment(
        self,
        attachment: Attachment,
    ) -> Attachment:

        return await self.create(
            attachment
        )

    # ==========================================================
    # Get By ID
    # ==========================================================

    async def get_by_id(
        self,
        attachment_id: UUID,
    ) -> Attachment | None:

        result = await self.execute(

            select(Attachment).where(

                Attachment.id == attachment_id

            )

        )

        return result.scalar_one_or_none()

    # ==========================================================
    # Get Message Attachments
    # ==========================================================

    async def get_by_message(
        self,
        message_id: UUID,
    ):

        result = await self.execute(

            select(Attachment)

            .where(
                Attachment.message_id == message_id
            )

        )

        return result.scalars().all()

    # ==========================================================
    # Delete
    # ==========================================================

    async def delete_attachment(
        self,
        attachment: Attachment,
    ):

        await self.delete(
            attachment
        )
