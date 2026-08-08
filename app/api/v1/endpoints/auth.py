"""Authentication endpoints — login, register, token refresh, logout."""

from fastapi import APIRouter, Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.cache.redis import redis_manager
from app.core.constants import REDIS_SESSION_PREFIX
from app.core.dependencies import get_current_user_id, get_db
from app.core.logging import get_logger
from app.core.security import decode_token
from app.schemas.auth import (
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
)
from app.schemas.auth import (
    LoginResponse as LoginResponseSchema,
)
from app.schemas.common import MessageResponse
from app.schemas.user import UserResponse
from app.services.auth_service import AuthService

logger = get_logger(__name__)
_bearer = HTTPBearer(auto_error=False)

router = APIRouter()


@router.post(
    "/login",
    summary="User login",
    description="Authenticate with email and password to receive JWT tokens.",
    response_model=LoginResponseSchema,
)
async def login(
    body: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> LoginResponseSchema:
    """Authenticate a user and return JWT tokens."""
    service = AuthService(db)
    return await service.authenticate(email=body.email, password=body.password)  # type: ignore[return-value]


@router.post(
    "/register",
    summary="User registration",
    description="Create a new user account.",
    response_model=UserResponse,
    status_code=201,
)
async def register(
    body: RegisterRequest,
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    """Register a new user."""
    service = AuthService(db)
    return await service.register(
        email=body.email,
        username=body.username,
        password=body.password,
        full_name=body.full_name,
    )


@router.post(
    "/refresh",
    summary="Refresh token",
    description="Exchange a valid refresh token for new JWT tokens.",
    response_model=TokenResponse,
)
async def refresh(
    body: RefreshRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """Refresh an expired access token using a refresh token."""
    service = AuthService(db)
    return await service.refresh_token(refresh_token=body.refresh_token)


@router.post(
    "/logout",
    summary="User logout",
    description="Blacklist the current access token so it cannot be reused.",
    response_model=MessageResponse,
)
async def logout(
    user_id: str = Depends(get_current_user_id),
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> MessageResponse:
    """Log out the current user by blacklisting their token in Redis."""
    if credentials:
        try:

            payload = decode_token(credentials.credentials)
            jti = payload.get("jti")
            exp = payload.get("exp", 0)
            if jti and exp:
                import time

                ttl = max(1, int(exp - time.time()))
                blacklist_key = f"{REDIS_SESSION_PREFIX}blacklist:{jti}"
                await redis_manager.set(blacklist_key, "1", ttl=ttl)
        except Exception as e:
            logger.warning("Token blacklisting failed (non-fatal)", error=str(e))

    return MessageResponse(
        message="Logged out successfully",
        code="logout_success",
    )


@router.get(
    "/me",
    summary="Get current user",
    description="Return the authenticated user's profile.",
    response_model=UserResponse,
)
async def get_me(
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    """Get the current authenticated user's profile."""
    service = AuthService(db)
    return await service.get_user_by_id(user_id)
