from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


# ---------- Requests ----------

class SendOTPRequest(BaseModel):
    """
    Request to send an OTP to the user's email.
    """

    email: EmailStr


class VerifyOTPRequest(BaseModel):
    """
    Request to verify an OTP.
    """

    email: EmailStr
    otp: str = Field(
        min_length=6,
        max_length=6,
        description="6-digit OTP code"
    )


class RefreshTokenRequest(BaseModel):
    """
    Request to refresh JWT tokens.
    """

    refresh_token: str


# ---------- Responses ----------

class MessageResponse(BaseModel):
    """
    Generic API response.
    """

    success: bool
    message: str


class TokenResponse(BaseModel):
    """
    JWT tokens returned after successful authentication.
    """

    access_token: str
    refresh_token: str
    token_type: str = "Bearer"


class UserResponse(BaseModel):
    """
    Public user information returned by the API.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: EmailStr
    username: str
    display_name: str
    avatar_url: str | None = None
    bio: str | None = None
    is_verified: bool
    online_status: str
    last_seen: datetime | None
    created_at: datetime