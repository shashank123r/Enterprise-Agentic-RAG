"""Authentication service — login, register, token refresh, user lookup."""

from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    AuthenticationError,
    ConflictError,
    NotFoundError,
)
from app.core.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    verify_password,
    verify_token,
)
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.auth import LoginResponse, TokenResponse
from app.schemas.user import UserResponse


class AuthService:
    """Authentication business logic."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repository = UserRepository(db)

    async def authenticate(
        self,
        email: str,
        password: str,
    ) -> TokenResponse:
        """Authenticate a user with email and password.

        Args:
            email: User's email address.
            password: User's plaintext password.

        Returns:
            TokenResponse with access and refresh tokens.

        Raises:
            AuthenticationError: If credentials are invalid.
        """
        user = await self.repository.get_by_email(email.lower().strip())
        if user is None:
            raise AuthenticationError(
                message="Invalid email or password",
                code="invalid_credentials",
            )

        if not user.is_active:
            raise AuthenticationError(
                message="Account is deactivated",
                code="account_disabled",
            )

        if not verify_password(password, user.hashed_password):
            raise AuthenticationError(
                message="Invalid email or password",
                code="invalid_credentials",
            )

        tokens = await self._generate_tokens(user)
        return LoginResponse(
            access_token=tokens.access_token,
            refresh_token=tokens.refresh_token,
            token_type=tokens.token_type,
            expires_in=tokens.expires_in,
            user=UserResponse.model_validate(user),
        )

    async def register(
        self,
        email: str,
        username: str,
        password: str,
        full_name: str | None = None,
    ) -> UserResponse:
        """Register a new user.

        Args:
            email: User's email address.
            username: Desired username.
            password: Plaintext password (will be hashed).
            full_name: Optional display name.

        Returns:
            UserResponse with user details.

        Raises:
            ConflictError: If email or username already exists.
        """
        existing_email = await self.repository.get_by_email(email.lower().strip())
        if existing_email is not None:
            raise ConflictError(
                message="A user with this email already exists",
                code="email_taken",
            )

        existing_username = await self.repository.get_by_username(username)
        if existing_username is not None:
            raise ConflictError(
                message="This username is already taken",
                code="username_taken",
            )

        hashed = hash_password(password)
        user = await self.repository.create(
            email=email.lower().strip(),
            username=username,
            hashed_password=hashed,
            full_name=full_name,
        )

        return UserResponse.model_validate(user)

    async def refresh_token(self, refresh_token: str) -> TokenResponse:
        """Exchange a refresh token for new access and refresh tokens.

        Args:
            refresh_token: Valid refresh JWT.

        Returns:
            TokenResponse with new tokens.
        """
        try:
            payload = verify_token(refresh_token, expected_type="refresh")
        except (JWTError, ValueError) as e:
            raise AuthenticationError(
                message="Invalid or expired refresh token",
                code="invalid_refresh_token",
            ) from e

        user_id = payload.get("sub")
        user = await self.repository.get_by_id(user_id)
        if user is None:
            raise AuthenticationError(
                message="User not found",
                code="user_not_found",
            )

        if not user.is_active:
            raise AuthenticationError(
                message="Account is deactivated",
                code="account_disabled",
            )

        return await self._generate_tokens(user)

    async def get_user_by_id(self, user_id: str) -> UserResponse:
        """Get a user by ID.

        Args:
            user_id: User UUID string.

        Returns:
            UserResponse.

        Raises:
            NotFoundError: If user doesn't exist.
        """
        user = await self.repository.get_by_id(user_id)
        if user is None:
            raise NotFoundError(
                message="User not found",
                code="user_not_found",
            )
        return UserResponse.model_validate(user)

    async def _generate_tokens(self, user: User) -> TokenResponse:
        """Generate access and refresh tokens for a user."""
        extra_claims = {
            "role": user.role,
            "email": user.email,
        }

        access_token = create_access_token(
            subject=user.id,
            extra_claims=extra_claims,
        )
        refresh_token = create_refresh_token(subject=user.id)

        from app.core.config import settings

        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )
