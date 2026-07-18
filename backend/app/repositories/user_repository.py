from sqlalchemy import or_, select

from app.models.user import User
from app.repositories.base_repository import BaseRepository


class UserRepository(BaseRepository):
    """
    Repository for user-related database operations.
    """

    # ==========================================================
    # Get User by ID
    # ==========================================================

    async def get_by_id(
        self,
        user_id,
    ) -> User | None:

        result = await self.execute(
            select(User).where(User.id == user_id)
        )

        return result.scalar_one_or_none()

    # ==========================================================
    # Get User by Email
    # ==========================================================

    async def get_by_email(
        self,
        email: str,
    ) -> User | None:

        result = await self.execute(
            select(User).where(User.email == email)
        )

        return result.scalar_one_or_none()

    # ==========================================================
    # Get User by Username
    # ==========================================================

    async def get_by_username(
        self,
        username: str,
    ) -> User | None:

        result = await self.execute(
            select(User).where(User.username == username)
        )

        return result.scalar_one_or_none()

    # ==========================================================
    # Search Users
    # ==========================================================

    async def search_users(
        self,
        query: str,
        limit: int = 20,
    ) -> list[User]:

        result = await self.execute(
            select(User)
            .where(
                or_(
                    User.username.ilike(f"%{query}%"),
                    User.display_name.ilike(f"%{query}%"),
                )
            )
            .limit(limit)
        )

        return result.scalars().all()

    # ==========================================================
    # Update User
    # ==========================================================

    async def update_user(
        self,
        user: User,
    ) -> User:
        """
        Commit changes made to an existing user and refresh it.
        """

        await self.update()
        await self.refresh(user)

        return user

    # ==========================================================
    # Delete User
    # ==========================================================

    async def delete_user(
        self,
        user: User,
    ) -> None:

        await self.delete(user)