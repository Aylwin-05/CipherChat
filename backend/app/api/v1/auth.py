from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db
from app.repositories.auth_repository import AuthRepository
from app.schemas.auth import (
    MessageResponse,
    SendOTPRequest,
    TokenResponse,
    VerifyOTPRequest,
    RefreshTokenRequest,
)
from app.services.auth_service import AuthService
from app.services.jwt_service import JWTService

router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
)


# ==========================================================
# Send OTP
# ==========================================================

@router.post(
    "/send-otp",
    response_model=MessageResponse,
)
async def send_otp(
    request: SendOTPRequest,
    db: AsyncSession = Depends(get_db),
):

    repository = AuthRepository(db)

    service = AuthService(repository)

    await service.send_otp(
        request.email,
    )

    return MessageResponse(
        success=True,
        message="OTP sent successfully.",
    )


# ==========================================================
# Verify OTP
# ==========================================================

@router.post(
    "/verify-otp",
    response_model=TokenResponse,
)
async def verify_otp(
    request: VerifyOTPRequest,
    db: AsyncSession = Depends(get_db),
):

    repository = AuthRepository(db)

    service = AuthService(repository)

    jwt = JWTService()

    result = await service.verify_otp(
        request.email,
        request.otp,
    )

    if result is None:

        raise HTTPException(
            status_code=400,
            detail="Invalid or expired OTP.",
        )

    user = result["user"]

    access_token = jwt.create_access_token(
        user_id=str(user.id),
        email=user.email,
    )

    refresh_token = jwt.create_refresh_token(
        user_id=str(user.id),
        email=user.email,
    )

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user=user,
    )

# ==========================================================
# Refresh Access Token
# ==========================================================

@router.post(
    "/refresh",
)
async def refresh_token(
    request: RefreshTokenRequest,
    db: AsyncSession = Depends(get_db),
):

    repository = AuthRepository(db)

    jwt_service = JWTService()

    payload = jwt_service.verify_refresh_token(
        request.refresh_token
    )

    if payload is None:

        raise HTTPException(
            status_code=401,
            detail="Invalid refresh token.",
        )

    user = await repository.get_user_by_id(
        payload["sub"]
    )

    if user is None:

        raise HTTPException(
            status_code=401,
            detail="User not found.",
        )

    access_token = jwt_service.create_access_token(
        user_id=str(user.id),
        email=user.email,
    )

    return {
        "access_token": access_token
    }