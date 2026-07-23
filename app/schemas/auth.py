"""Auth-related Pydantic V2 schemas."""

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.schemas.user import UserResponse


class LoginRequest(BaseModel):
    """User login request body."""

    email: EmailStr = Field(..., description="Registered email address")
    password: str = Field(..., min_length=8, max_length=128, description="Account password")


class RegisterRequest(BaseModel):
    """User registration request body."""

    email: EmailStr = Field(..., description="Email address")
    username: str = Field(
        ...,
        min_length=3,
        max_length=150,
        pattern=r"^[a-zA-Z0-9_-]+$",
        description="Unique username (alphanumeric, hyphens, underscores)",
    )
    password: str = Field(
        ...,
        min_length=8,
        max_length=128,
        description="Password (min 8 characters)",
    )
    full_name: str | None = Field(None, max_length=255, description="Display name")

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        """Ensure username is lowercase."""
        return v.lower().strip()


class TokenResponse(BaseModel):
    """JWT token response."""

    access_token: str = Field(..., description="JWT access token")
    refresh_token: str = Field(..., description="JWT refresh token")
    token_type: str = Field("bearer", description="Token type")
    expires_in: int = Field(..., description="Access token TTL in seconds")


class LoginResponse(TokenResponse):
    """Login response includes tokens + user info."""

    user: UserResponse = Field(..., description="Authenticated user profile")


class RefreshRequest(BaseModel):
    """Token refresh request body."""

    refresh_token: str = Field(..., description="Valid refresh token")


class TokenPayload(BaseModel):
    """Decoded JWT token payload (for internal use)."""

    sub: str = Field(..., description="Subject (user ID)")
    iss: str = Field(..., description="Issuer")
    aud: str = Field(..., description="Audience")
    iat: int = Field(..., description="Issued at (epoch)")
    exp: int = Field(..., description="Expiration (epoch)")
    type: str = Field(..., description="Token type: access or refresh")
    role: str | None = Field(None, description="User role")
