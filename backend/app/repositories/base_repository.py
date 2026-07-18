from typing import Generic, TypeVar

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

ModelType = TypeVar("ModelType")


class BaseRepository(Generic[ModelType]):
    """
    Generic repository containing common database operations.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    # ======================================================
    # Create
    # ======================================================

    async def create(self, obj: ModelType) -> ModelType:
        self.db.add(obj)

        await self.db.commit()
        await self.db.refresh(obj)

        return obj

    # ======================================================
    # Update
    # ======================================================

    async def update(self) -> None:
        await self.db.commit()

    # ======================================================
    # Delete
    # ======================================================

    async def delete(self, obj: ModelType) -> None:
        await self.db.delete(obj)
        await self.db.commit()

    # ======================================================
    # Refresh
    # ======================================================

    async def refresh(self, obj: ModelType):
        await self.db.refresh(obj)

    # ======================================================
    # Execute
    # ======================================================

    async def execute(self, stmt: Select):
        return await self.db.execute(stmt)