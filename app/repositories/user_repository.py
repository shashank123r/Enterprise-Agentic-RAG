"""User repository — database queries for the User model."""

from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    """Repository for User-specific database operations."""

    def __init__(self, db: AsyncSession) -> None:
        super().__init__(db, User)

    async def get_by_email(self, email: str) -> User | None:
        """Get a user by their email address."""
        stmt = select(User).where(User.email == email)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_username(self, username: str) -> User | None:
        """Get a user by their username."""
        stmt = select(User).where(User.username == username)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_users(
        self,
        page: int = 1,
        size: int = 20,
        role: str | None = None,
    ) -> tuple[Sequence[User], int]:
        """List users with pagination and optional role filter.

        Args:
            page: Page number (1-indexed).
            size: Items per page.
            role: Optional role string to filter by.

        Returns:
            Tuple of (list of users, total count).
        """
        base_query = select(User)

        if role:
            base_query = base_query.where(User.role == role)

        # Count total
        count_query = select(func.count()).select_from(base_query.subquery())
        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        # Fetch page
        offset = (page - 1) * size
        fetch_query = base_query.order_by(User.created_at.desc()).offset(offset).limit(size)
        result = await self.db.execute(fetch_query)
        users = list(result.scalars().all())

        return users, total

    async def update_last_login(self, user_id: str) -> None:
        """Update the user's last login timestamp."""
        from datetime import UTC, datetime

        await self.update(user_id, updated_at=datetime.now(UTC))

    async def activate_user(self, user_id: str) -> User:
        """Activate a deactivated user."""
        return await self.update(user_id, is_active=True)

    async def deactivate_user(self, user_id: str) -> User:
        """Deactivate an active user."""
        return await self.update(user_id, is_active=False)

    async def verify_email(self, user_id: str) -> User:
        """Mark a user's email as verified."""
        return await self.update(user_id, is_verified=True)

    async def change_role(self, user_id: str, new_role: str) -> User:
        """Change a user's role."""
        return await self.update(user_id, role=new_role)
