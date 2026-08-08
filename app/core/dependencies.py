"""FastAPI dependency injection providers.

All dependencies are wired here for Clean Architecture and testability.
"""

from collections.abc import AsyncGenerator
from typing import Any

import structlog
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import ROLE_PERMISSIONS, Permission, Role
from app.core.exceptions import AuthenticationError, AuthorizationError
from app.core.security import decode_token
from app.db.session import async_session_factory
from app.storage import StorageProvider
from app.storage.factory import get_storage_provider as _get_storage_provider
from app.vector_stores import VectorStore
from app.vector_stores.collection_manager import CollectionManager
from app.vector_stores.factory import (
    get_collection_manager as _get_collection_manager,
)
from app.vector_stores.factory import (
    get_vector_store as _get_vector_store,
)


async def get_storage() -> StorageProvider:
    """FastAPI dependency that provides the configured StorageProvider.

    Usage:
        @router.post("/upload")
        async def upload(
            storage: StorageProvider = Depends(get_storage),
            ...
        ):
            ...
    """
    return await _get_storage_provider()


# ── Vector Store DI ───────────────────────────


async def get_vector_store() -> AsyncGenerator[VectorStore]:
    """FastAPI dependency — provides the singleton VectorStore."""
    async for store in _get_vector_store():
        yield store


async def get_collection_manager() -> AsyncGenerator[CollectionManager]:
    """FastAPI dependency — provides the CollectionManager."""
    async for manager in _get_collection_manager():
        yield manager


# ── Auth scheme ───────────────────────────────
bearer_scheme = HTTPBearer(auto_error=False)


async def get_db() -> AsyncGenerator[AsyncSession]:
    """Provide an async database session.

    Yields:
        An SQLAlchemy async session. Rolled back on exception.
    """
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def _extract_token_payload(
    credentials: HTTPAuthorizationCredentials | None,
) -> dict[str, Any]:
    """Extract and validate the JWT payload once, returning claims dict.

    This is the single point of token extraction — used by all auth
    dependencies to avoid redundant JWT decoding. Also checks the
    Redis blacklist to reject logged-out tokens.
    """
    if credentials is None:
        raise AuthenticationError(
            message="Authentication required",
            code="missing_token",
        )

    try:
        payload = decode_token(credentials.credentials)

        # Check token blacklist (for logged-out tokens)
        jti = payload.get("jti")
        if jti:
            from app.cache.redis import redis_manager
            from app.core.constants import REDIS_SESSION_PREFIX

            blacklist_key = f"{REDIS_SESSION_PREFIX}blacklist:{jti}"
            try:
                is_blacklisted = await redis_manager.get(blacklist_key)
                if is_blacklisted:
                    raise AuthenticationError(
                        message="Token has been revoked",
                        code="token_revoked",
                    )
            except AuthenticationError:
                raise
            except Exception:
                pass  # Redis down — fail open for availability

        # Propagate request_id to structlog context for traceability
        structlog.contextvars.bind_contextvars(
            user_id=payload.get("sub", "unknown"),
            user_role=payload.get("role", "unknown"),
        )

        return payload
    except AuthenticationError:
        raise
    except JWTError:
        raise AuthenticationError(
            message="Invalid or expired token",
            code="invalid_token",
        )


async def get_current_user_id(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> str:
    """Extract and validate the current user ID from JWT.

    Returns:
        User ID (UUID string) from the token.
    """
    payload = await _extract_token_payload(credentials)
    user_id = payload.get("sub")
    if user_id is None:
        raise AuthenticationError(
            message="Invalid token payload",
            code="invalid_token",
        )
    return user_id


async def get_current_user_role(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> Role:
    """Extract the user's role from JWT claims for RBAC."""
    payload = await _extract_token_payload(credentials)
    role_str = payload.get("role", "viewer")
    try:
        return Role(role_str)
    except ValueError:
        raise AuthenticationError(
            message="Invalid role in token",
            code="invalid_token",
        )


async def get_current_user_payload(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> dict[str, Any]:
    """Get the full decoded JWT payload (optimized — single decode).

    Use this when both user_id and role are needed to avoid double JWT decode.
    """
    return await _extract_token_payload(credentials)


def require_permission(required: Permission):
    """Dependency factory: require a specific permission.

    Usage:
        @router.get("/users")
        async def list_users(
            _=Depends(require_permission(Permission.USER_READ)),
        ):
            ...
    """

    async def _permission_checker(
        role: Role = Depends(get_current_user_role),
    ) -> Role:
        permissions = ROLE_PERMISSIONS.get(role, set())
        if required not in permissions:
            raise AuthorizationError(
                message=f"Missing required permission: {required.value}",
                code="insufficient_permissions",
                details={"required": required.value, "role": role.value},
            )
        return role

    return _permission_checker


def require_role(minimum_role: Role):
    """Dependency factory: require at minimum a specific role.

    Usage:
        @router.get("/admin/dashboard")
        async def dashboard(
            _=Depends(require_role(Role.ADMIN)),
        ):
            ...
    """

    async def _role_checker(
        role: Role = Depends(get_current_user_role),
    ) -> Role:
        role_hierarchy = list(Role)
        min_index = role_hierarchy.index(minimum_role)
        actual_index = role_hierarchy.index(role)

        if actual_index > min_index:
            raise AuthorizationError(
                message=(
                    f"Role '{role.value}' is below minimum " f"required '{minimum_role.value}'"
                ),
                code="insufficient_role",
                details={
                    "required": minimum_role.value,
                    "actual": role.value,
                },
            )
        return role

    return _role_checker
