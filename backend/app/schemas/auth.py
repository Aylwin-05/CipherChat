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
    """
    Request to send an OTP.
    """

    email: EmailStr


class VerifyOTPRequest(BaseModel):
    """
    Request to verify OTP.
    """

    email: EmailStr
    otp: OTPCode


class RefreshTokenRequest(BaseModel):
    """
    Refresh JWT token request.
    """

    refresh_token: str


# ==========================================================
# Responses
# ==========================================================

class MessageResponse(BaseModel):
    """
    Generic API response.
    """

    success: bool
    message: str


class SendOTPResponse(MessageResponse):
    """
    Response after sending OTP.
    """

    pass


class TokenResponse(BaseModel):
    """
    JWT response.
    """

    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
