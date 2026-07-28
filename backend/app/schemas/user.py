from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


# ==========================================================
# Public User
# ==========================================================

class UserResponse(BaseModel):
    """
    Public user information.
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

    last_seen: datetime | None = None

    created_at: datetime



# ==========================================================
# Update Profile
# ==========================================================

class UpdateProfileRequest(BaseModel):

    display_name: Optional[str] = Field(
        default=None,
        min_length=2,
        max_length=50,
    )

    bio: Optional[str] = Field(
        default=None,
        max_length=250,
    )

    avatar_url: Optional[str] = None


# ==========================================================
# Search Users
# ==========================================================

class SearchUserResponse(BaseModel):

    model_config = ConfigDict(from_attributes=True)

    id: UUID

    username: str

    display_name: str

    avatar_url: str | None = None

    online_status: str



# ==========================================================
# Username Availability
# ==========================================================

class UsernameAvailabilityResponse(BaseModel):

    available: bool

    message: str