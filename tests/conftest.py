"""Pytest configuration — fixtures for FastAPI test client, database, and authentication."""

import os
from collections.abc import AsyncGenerator
from typing import Any
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import NullPool, text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings
from app.core.constants import Role
from app.core.dependencies import get_db
from app.core.security import create_access_token, hash_password
from app.db.base import Base
from app.main import create_app

# Use a test database — overridable via env var
TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    settings.database_url + "_test",
)


@pytest.fixture(scope="session")
def event_loop():
    """Create an event loop for the test session."""
    import asyncio

    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session")
async def test_engine():
    """Create a test engine with separate database."""
    engine = create_async_engine(
        TEST_DATABASE_URL,
        echo=False,
        poolclass=NullPool,
    )

    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    # Drop tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(test_engine) -> AsyncGenerator[AsyncSession]:
    """Provide a clean database session for each test."""
    session_factory = async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with session_factory() as session:
        try:
            yield session
        finally:
            # Rollback any uncommitted changes
            await session.rollback()
            # Clean all tables after each test
            for table in reversed(Base.metadata.sorted_tables):
                await session.execute(text(f"TRUNCATE {table.name} CASCADE"))
            await session.commit()
            await session.close()


@pytest_asyncio.fixture
async def app(test_engine) -> FastAPI:
    """Create the FastAPI application with test dependencies."""
    application = create_app()

    # Override the database session dependency
    async def override_get_db() -> AsyncGenerator[AsyncSession]:
        session_factory = async_sessionmaker(
            test_engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    application.dependency_overrides[get_db] = override_get_db
    return application


@pytest_asyncio.fixture
async def client(app: FastAPI) -> AsyncGenerator[AsyncClient]:
    """Provide an async HTTP test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
    ) as async_client:
        yield async_client


@pytest.fixture
def test_user_data() -> dict[str, Any]:
    """Default test user data."""
    return {
        "email": "test@example.com",
        "username": "testuser",
        "password": "TestPassword123!",
        "full_name": "Test User",
    }


@pytest.fixture
def admin_user_data() -> dict[str, Any]:
    """Default admin user data."""
    return {
        "email": "admin@example.com",
        "username": "adminuser",
        "password": "AdminPassword123!",
        "full_name": "Admin User",
    }


@pytest_asyncio.fixture
async def test_user(
    db_session: AsyncSession,
    test_user_data: dict[str, Any],
) -> dict[str, Any]:
    """Create and return a test user in the database."""
    from app.models.user import User

    user = User(
        id=str(uuid4()),
        email=test_user_data["email"],
        username=test_user_data["username"],
        hashed_password=hash_password(test_user_data["password"]),
        full_name=test_user_data["full_name"],
        role=Role.USER.value,
        is_active=True,
        is_verified=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    return {
        "id": user.id,
        "email": user.email,
        "username": user.username,
        "password": test_user_data["password"],
        "role": user.role,
    }


@pytest_asyncio.fixture
async def admin_user(
    db_session: AsyncSession,
    admin_user_data: dict[str, Any],
) -> dict[str, Any]:
    """Create and return an admin user in the database."""
    from app.models.user import User

    user = User(
        id=str(uuid4()),
        email=admin_user_data["email"],
        username=admin_user_data["username"],
        hashed_password=hash_password(admin_user_data["password"]),
        full_name=admin_user_data["full_name"],
        role=Role.ADMIN.value,
        is_active=True,
        is_verified=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    return {
        "id": user.id,
        "email": user.email,
        "username": user.username,
        "password": admin_user_data["password"],
        "role": user.role,
    }


@pytest.fixture
def user_token(test_user: dict[str, Any]) -> str:
    """Generate a JWT access token for the test user."""
    return create_access_token(
        subject=test_user["id"],
        extra_claims={"role": test_user["role"]},
    )


@pytest.fixture
def admin_token(admin_user: dict[str, Any]) -> str:
    """Generate a JWT access token for the admin user."""
    return create_access_token(
        subject=admin_user["id"],
        extra_claims={"role": admin_user["role"]},
    )


@pytest.fixture
def auth_header(user_token: str) -> dict[str, str]:
    """Authorization header for the test user."""
    return {"Authorization": f"Bearer {user_token}"}


@pytest.fixture
def admin_auth_header(admin_token: str) -> dict[str, str]:
    """Authorization header for the admin user."""
    return {"Authorization": f"Bearer {admin_token}"}
