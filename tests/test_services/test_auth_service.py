"""Unit tests for the AuthService."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AuthenticationError, ConflictError
from app.services.auth_service import AuthService


@pytest.mark.asyncio
async def test_register_user_service(db_session: AsyncSession) -> None:
    """Test successful user registration via AuthService."""
    service = AuthService(db_session)
    result = await service.register(
        email="service@example.com",
        username="serviceuser",
        password="SecurePass123!",
        full_name="Service User",
    )
    assert result.email == "service@example.com"
    assert result.username == "serviceuser"
    assert result.role == "user"
    assert result.is_active is True


@pytest.mark.asyncio
async def test_register_duplicate_email(
    db_session: AsyncSession,
    test_user: dict,
) -> None:
    """Test that registering with an existing email raises ConflictError."""
    service = AuthService(db_session)
    with pytest.raises(ConflictError) as exc_info:
        await service.register(
            email=test_user["email"],
            username="anotheruser",
            password="SecurePass123!",
        )
    assert exc_info.value.code == "email_taken"


@pytest.mark.asyncio
async def test_authenticate_success(
    db_session: AsyncSession,
    test_user: dict,
) -> None:
    """Test successful authentication returns tokens."""
    service = AuthService(db_session)
    tokens = await service.authenticate(
        email=test_user["email"],
        password=test_user["password"],
    )
    assert tokens.access_token is not None
    assert tokens.refresh_token is not None
    assert tokens.token_type == "bearer"


@pytest.mark.asyncio
async def test_authenticate_wrong_password(
    db_session: AsyncSession,
    test_user: dict,
) -> None:
    """Test authentication with wrong password raises AuthenticationError."""
    service = AuthService(db_session)
    with pytest.raises(AuthenticationError) as exc_info:
        await service.authenticate(
            email=test_user["email"],
            password="WrongPassword123!",
        )
    assert exc_info.value.code == "invalid_credentials"


@pytest.mark.asyncio
async def test_authenticate_nonexistent_user(db_session: AsyncSession) -> None:
    """Test authentication with unregistered email raises AuthenticationError."""
    service = AuthService(db_session)
    with pytest.raises(AuthenticationError):
        await service.authenticate(
            email="nobody@example.com",
            password="SomePass123!",
        )


@pytest.mark.asyncio
async def test_get_user_by_id(
    db_session: AsyncSession,
    test_user: dict,
) -> None:
    """Test getting a user by ID via AuthService."""
    service = AuthService(db_session)
    result = await service.get_user_by_id(test_user["id"])
    assert result.id == test_user["id"]
    assert result.email == test_user["email"]


@pytest.mark.asyncio
async def test_refresh_token_valid(
    db_session: AsyncSession,
    test_user: dict,
) -> None:
    """Test refreshing tokens with a valid refresh token."""
    service = AuthService(db_session)

    # First authenticate to get tokens
    tokens = await service.authenticate(
        email=test_user["email"],
        password=test_user["password"],
    )

    # Refresh
    new_tokens = await service.refresh_token(tokens.refresh_token)
    assert new_tokens.access_token is not None
    assert new_tokens.refresh_token is not None
    assert new_tokens.access_token != tokens.access_token
