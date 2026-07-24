from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


# ==========================================================
# Reusable Types
# ==========================================================

OTPCode = Annotated[
    str,
    Field(
        pattern=r"^\d{6}$",
        description="6-digit OTP",
    ),
]


# ==========================================================
# Requests
# ==========================================================

class SendOTPRequest(BaseModel):

    email: EmailStr


class VerifyOTPRequest(BaseModel):

    email: EmailStr

    otp: OTPCode


class RefreshTokenRequest(BaseModel):

    refresh_token: str


# ==========================================================
# User Response
# ==========================================================

class UserResponse(BaseModel):

    model_config = ConfigDict(
        from_attributes=True,
    )

    id: UUID

    email: EmailStr

    username: str

    display_name: str

    bio: str | None = None

    avatar_url: str | None = None

    is_verified: bool

    is_active: bool

    online_status: str

    last_seen: datetime | None = None

    created_at: datetime

    updated_at: datetime


# ==========================================================
# Generic Responses
# ==========================================================

class MessageResponse(BaseModel):

    success: bool

    message: str


class SendOTPResponse(MessageResponse):
    pass


# ==========================================================
# Login Response
# ==========================================================

class TokenResponse(BaseModel):

    access_token: str

    refresh_token: str

    token_type: str = "Bearer"

    user: UserResponse