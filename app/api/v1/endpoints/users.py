"""User management endpoints — CRUD with RBAC."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, Permission, Role
from app.core.dependencies import (
    get_current_user_id,
    get_current_user_payload,
    get_db,
    require_permission,
    require_role,
)
from app.core.exceptions import AuthorizationError
from app.schemas.common import MessageResponse, PaginatedResponse
from app.schemas.user import UserAdminUpdate, UserResponse, UserUpdate
from app.services.user_service import UserService

router = APIRouter()


@router.get(
    "/",
    summary="List users",
    description="List all users with pagination. Admin only.",
    response_model=PaginatedResponse[UserResponse],
)
async def list_users(
    page: int = Query(default=1, ge=1, description="Page number"),
    size: int = Query(
        default=DEFAULT_PAGE_SIZE,
        ge=1,
        le=MAX_PAGE_SIZE,
        description="Items per page",
    ),
    role: str | None = Query(default=None, description="Filter by role"),
    _admin: Role = Depends(require_role(Role.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> PaginatedResponse[UserResponse]:
    """List all users with pagination (admin only)."""
    service = UserService(db)
    return await service.list_users(page=page, size=size, role=role)


@router.get(
    "/{user_id}",
    summary="Get user by ID",
    description="Retrieve a specific user's profile.",
    response_model=UserResponse,
)
async def get_user(
    user_id: str,
    payload: dict = Depends(get_current_user_payload),
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    """Get a user by ID. Users can get their own profile; admins can get any."""
    current_user_id = payload["sub"]
    current_role = Role(payload.get("role", "viewer"))

    if user_id != current_user_id and current_role != Role.ADMIN:
        raise AuthorizationError(
            message="Cannot access another user's profile",
            code="insufficient_permissions",
        )
    service = UserService(db)
    return await service.get_user_by_id(user_id)


@router.patch(
    "/me",
    summary="Update own profile",
    description="Update the authenticated user's profile.",
    response_model=UserResponse,
)
async def update_me(
    body: UserUpdate,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    """Update the current user's profile."""
    service = UserService(db)
    return await service.update_user(user_id=user_id, data=body)


@router.patch(
    "/{user_id}",
    summary="Admin update user",
    description="Admin-level user update (role, active status, etc.).",
    response_model=UserResponse,
)
async def admin_update_user(
    user_id: str,
    body: UserAdminUpdate,
    _perm: Role = Depends(require_permission(Permission.USER_UPDATE)),
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    """Admin-level update for any user."""
    service = UserService(db)
    return await service.admin_update_user(user_id=user_id, data=body)


@router.delete(
    "/{user_id}",
    summary="Delete user",
    description="Permanently delete a user account. Admin only.",
    response_model=MessageResponse,
)
async def delete_user(
    user_id: str,
    _perm: Role = Depends(require_permission(Permission.USER_DELETE)),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """Delete a user (admin only)."""
    service = UserService(db)
    await service.delete_user(user_id)
    return MessageResponse(message="User deleted successfully", code="user_deleted")
