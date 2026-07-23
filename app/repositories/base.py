"""Generic repository base with common CRUD operations.

Uses SQLAlchemy 2.0 style async queries.
"""

from typing import Any, Generic, TypeVar

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import Base

ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository(Generic[ModelT]):
    """Generic repository with common database operations.

    Type-parameterized for type-safe CRUD on any ORM model.
    """

    def __init__(self, db: AsyncSession, model: type[ModelT]) -> None:
        self.db = db
        self.model = model

    async def get_by_id(self, id: str) -> ModelT | None:
        """Get a record by its UUID primary key."""
        stmt = select(self.model).where(self.model.id == id)  # type: ignore[attr-defined]
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_all(
        self,
        skip: int = 0,
        limit: int = 100,
        order_by: str | None = None,
    ) -> list[ModelT]:
        """List all records with pagination."""
        stmt = select(self.model).offset(skip).limit(limit)
        if order_by:
            stmt = stmt.order_by(order_by)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def count(self, filters: dict[str, Any] | None = None) -> int:
        """Count records, optionally with filters."""
        from sqlalchemy import func

        stmt = select(func.count()).select_from(self.model)
        if filters:
            for key, value in filters.items():
                stmt = stmt.where(getattr(self.model, key) == value)
        result = await self.db.execute(stmt)
        return result.scalar() or 0

    async def create(self, **kwargs: Any) -> ModelT:
        """Create a new record."""
        instance = self.model(**kwargs)
        self.db.add(instance)
        await self.db.flush()
        await self.db.refresh(instance)
        return instance

    async def update(self, id: str, **kwargs: Any) -> ModelT:
        """Update a record by ID. Returns the updated record.

        Only updates fields that are provided.
        """
        stmt = (
            update(self.model)
            .where(self.model.id == id)  # type: ignore[attr-defined]
            .values(**kwargs)
            .returning(self.model)
        )
        result = await self.db.execute(stmt)
        await self.db.flush()
        return result.scalar_one()

    async def delete(self, id: str) -> None:
        """Delete a record by ID."""
        stmt = delete(self.model).where(self.model.id == id)  # type: ignore[attr-defined]
        await self.db.execute(stmt)
        await self.db.flush()

    async def exists(self, **filters: Any) -> bool:
        """Check if a record exists matching the given filters."""
        stmt = select(self.model).filter_by(**filters).limit(1)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def find_by(self, **filters: Any) -> list[ModelT]:
        """Find records matching the given filters."""
        stmt = select(self.model).filter_by(**filters)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def find_one_by(self, **filters: Any) -> ModelT | None:
        """Find a single record matching the given filters."""
        stmt = select(self.model).filter_by(**filters).limit(1)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()
