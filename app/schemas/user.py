"""User-related Pydantic V2 schemas."""

from datetime import datetime

from pydantic import BaseModel, Field

from app.core.constants import Role


class UserResponse(BaseModel):
    """Public user information (response)."""

    id: str = Field(..., description="User UUID")
    email: str = Field(..., description="Email address")
    username: str = Field(..., description="Unique username")
    role: str = Field(..., description="User role")
    is_active: bool = Field(..., description="Whether the user is active")
    is_verified: bool = Field(..., description="Whether email is verified")
    full_name: str | None = Field(None, description="Display name")
    avatar_url: str | None = Field(None, description="Avatar URL")
    created_at: datetime = Field(..., description="Account creation time")
    updated_at: datetime = Field(..., description="Last update time")

    model_config = {"from_attributes": True}


class UserUpdate(BaseModel):
    """User profile update request."""

    full_name: str | None = Field(None, max_length=255, description="Display name")
    avatar_url: str | None = Field(None, max_length=1024, description="Avatar URL")


class UserAdminUpdate(BaseModel):
    """Admin-level user update request."""

    role: Role | None = Field(None, description="User role")
    is_active: bool | None = Field(None, description="Whether the user is active")
    is_verified: bool | None = Field(None, description="Whether email is verified")
