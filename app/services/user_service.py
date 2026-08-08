"""User service — CRUD operations with RBAC enforcement."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.repositories.user_repository import UserRepository
from app.schemas.common import PaginatedResponse
from app.schemas.user import UserAdminUpdate, UserResponse, UserUpdate


class UserService:
    """User management business logic."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repository = UserRepository(db)

    async def get_user_by_id(self, user_id: str) -> UserResponse:
        """Get a user by their UUID.

        Args:
            user_id: User UUID string.

        Returns:
            UserResponse.

        Raises:
            NotFoundError: If the user doesn't exist.
        """
        user = await self.repository.get_by_id(user_id)
        if user is None:
            raise NotFoundError(
                message="User not found",
                code="user_not_found",
            )
        return UserResponse.model_validate(user)

    async def list_users(
        self,
        page: int = 1,
        size: int = 20,
        role: str | None = None,
    ) -> PaginatedResponse[UserResponse]:
        """List users with pagination and optional role filter.

        Args:
            page: Page number (1-indexed).
            size: Items per page.
            role: Optional role filter.

        Returns:
            PaginatedResponse of UserResponse.
        """
        users, total = await self.repository.list_users(
            page=page,
            size=size,
            role=role,
        )
        items = [UserResponse.model_validate(u) for u in users]
        return PaginatedResponse.create(
            items=items,
            total=total,
            page=page,
            size=size,
        )

    async def update_user(
        self,
        user_id: str,
        data: UserUpdate,
    ) -> UserResponse:
        """Update a user's profile.

        Args:
            user_id: User UUID string.
            data: Fields to update.

        Returns:
            Updated UserResponse.
        """
        user = await self.repository.get_by_id(user_id)
        if user is None:
            raise NotFoundError(
                message="User not found",
                code="user_not_found",
            )

        updated = await self.repository.update(
            user_id,
            **data.model_dump(exclude_none=True),
        )
        return UserResponse.model_validate(updated)

    async def admin_update_user(
        self,
        user_id: str,
        data: UserAdminUpdate,
    ) -> UserResponse:
        """Admin-level update of a user.

        Args:
            user_id: User UUID string.
            data: Fields to update.

        Returns:
            Updated UserResponse.
        """
        user = await self.repository.get_by_id(user_id)
        if user is None:
            raise NotFoundError(
                message="User not found",
                code="user_not_found",
            )

        update_data = data.model_dump(exclude_none=True)
        updated = await self.repository.update(user_id, **update_data)
        return UserResponse.model_validate(updated)

    async def delete_user(self, user_id: str) -> None:
        """Delete a user permanently.

        Args:
            user_id: User UUID string.

        Raises:
            NotFoundError: If the user doesn't exist.
        """
        user = await self.repository.get_by_id(user_id)
        if user is None:
            raise NotFoundError(
                message="User not found",
                code="user_not_found",
            )

        await self.repository.delete(user_id)
