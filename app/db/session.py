"""SQLAlchemy async engine and session factory.

Uses asyncpg for async PostgreSQL connectivity.
"""

import orjson
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings

engine = create_async_engine(
    settings.database_url,
    echo=settings.POSTGRES_ECHO,
    pool_size=settings.POSTGRES_POOL_SIZE,
    max_overflow=settings.POSTGRES_MAX_OVERFLOW,
    pool_pre_ping=True,
    pool_recycle=3600,
    pool_use_lifo=True,
    json_serializer=lambda obj: orjson.dumps(obj).decode(),
    json_deserializer=lambda raw: orjson.loads(raw),
    connect_args={
        "timeout": 30,
        "command_timeout": 60,
    },
)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def init_db() -> None:
    """Test database connectivity at startup."""
    async with engine.begin() as conn:
        result = await conn.execute(text("SELECT 1"))
        assert result.scalar() == 1


async def shutdown_db() -> None:
    """Dispose of the database engine on shutdown."""
    await engine.dispose()
