from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.database import AsyncSessionLocal


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency that provides an AsyncSession.

    A new session is created for each request and is
    automatically closed after the request completes.
    """

    async with AsyncSessionLocal() as session:
        yield session