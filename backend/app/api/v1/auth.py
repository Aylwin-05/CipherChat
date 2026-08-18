from uuid import UUID

import logging

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
    Response,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
logger = logging.getLogger(__name__)
from app.core.rate_limit import (
    RateLimitExceeded,
    get_limiter,
)
from app.database.session import get_db
from app.dependencies.rate_limit import rate_limit
from app.repositories.auth_repository import AuthRepository
from app.repositories.refresh_token_repository import (
    RefreshTokenError,
    RefreshTokenRepository,
)
from app.schemas.auth import (
    MessageResponse,
    SendOTPRequest,
    TokenResponse,
    VerifyOTPRequest,
)
from app.services.auth_service import AuthService
from app.services.jwt_service import JWTService
from app.services.refresh_token_service import RefreshTokenService

router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
)

# ==========================================================
# Cookies
# ==========================================================

REFRESH_COOKIE_NAME = "cc_refresh"


def _set_refresh_cookie(
    response: Response,
    token: str,
):
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        path="/",
        domain=settings.COOKIE_DOMAIN,
    )


def _clear_refresh_cookie(response: Response):
    response.delete_cookie(
        key=REFRESH_COOKIE_NAME,
        path="/",
        domain=settings.COOKIE_DOMAIN,
    )


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _extract_refresh_token(
    request: Request,
    body_token: str | None,
) -> str:
    """Prefer the HttpOnly cookie; accept the body for mobile clients."""

    token = request.cookies.get(REFRESH_COOKIE_NAME)
    return token or body_token or ""


# ==========================================================
# Send OTP
# ==========================================================

@router.post(
    "/send-otp",
    response_model=MessageResponse,
    dependencies=[
        rate_limit("otp.send.ip", 50, 600),
    ],
)
async def send_otp(
    request: Request,
    request_body: SendOTPRequest,
    db: AsyncSession = Depends(get_db),
):

    repository = AuthRepository(db)

    service = AuthService(repository)

    # Per-email throttle: an attacker must not burn an account's
    # inbox (or the DB row) faster than the IP can.
    try:

        await get_limiter().check(
            f"otp.send.{request_body.email.lower()}",
            3,
            600,
        )

    except RateLimitExceeded as exc:

        raise HTTPException(
            status_code=429,
            detail="Too many requests. Try again later.",
            headers={"Retry-After": str(exc.retry_after)},
        )

    await service.send_otp(
        request_body.email,
        client_ip=_client_ip(request),
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
    dependencies=[
        rate_limit("otp.verify.ip", 50, 600),
    ],
)
async def verify_otp(
    request: Request,
    response: Response,
    request_body: VerifyOTPRequest,
    db: AsyncSession = Depends(get_db),
):

    repository = AuthRepository(db)

    service = AuthService(repository)

    jwt = JWTService()

    result = await service.verify_otp(
        request_body.email,
        request_body.otp,
    )

    if result is None:

        raise HTTPException(
            status_code=400,
            detail="Invalid or expired OTP.",
        )

    user = result["user"]
    logger.info(
        "OTP verified successfully: user=%s email=%s",
        user.id,
        user.email,
    )

    access_token = jwt.create_access_token(
        user_id=str(user.id),
        email=user.email,
    )

    # -- issue + persist refresh token (rotation-enabled) ---------
    refresh_service = RefreshTokenService(
        RefreshTokenRepository(db)
    )

    refresh_token = await refresh_service.issue(
        user.id,
        user_agent=request.headers.get("user-agent"),
        ip_address=_client_ip(request),
    )

    _set_refresh_cookie(response, refresh_token)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user=user,
    )


# ==========================================================
# Refresh Access Token (with rotation)
# ==========================================================

@router.post(
    "/refresh",
    dependencies=[
        rate_limit("auth.refresh.ip", 60, 600),
    ],
)
async def refresh_token(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):

    body_token = None
    if request.headers.get("content-type", "").startswith("application/json"):
        import json

        try:
            body_token = json.loads(
                (await request.body()).decode()
            ).get("refresh_token")
        except Exception:
            body_token = None

    token = _extract_refresh_token(request, body_token)

    if not token:

        raise HTTPException(
            status_code=401,
            detail="Missing refresh token.",
        )

    refresh_service = RefreshTokenService(
        RefreshTokenRepository(db)
    )

    try:

        new_token = await refresh_service.rotate(
            token,
            user_agent=request.headers.get("user-agent"),
            ip_address=_client_ip(request),
        )

    except RefreshTokenError as exc:

        # Rotate on reuse/expiry: caller must re-authenticate.
        _clear_refresh_cookie(response)

        raise HTTPException(
            status_code=401,
            detail=exc.args[0],
        )

    jwt = JWTService()

    payload = jwt.decode_token(new_token)

    user_id = payload["sub"]

    repository = AuthRepository(db)

    user = await repository.get_user_by_id(UUID(user_id))

    if user is None:

        raise HTTPException(
            status_code=401,
            detail="User not found.",
        )

    access_token = jwt.create_access_token(
        user_id=str(user.id),
        email=user.email,
    )

    _set_refresh_cookie(response, new_token)

    return {
        "access_token": access_token,
        "refresh_token": new_token,
        "token_type": "Bearer",
    }


# ==========================================================
# Logout (revoke the refresh-token family)
# ==========================================================

@router.post(
    "/logout",
    response_model=MessageResponse,
)
async def logout(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):

    body_token = None
    if request.headers.get("content-type", "").startswith("application/json"):
        import json

        try:
            body_token = json.loads(
                (await request.body()).decode()
            ).get("refresh_token")
        except Exception:
            body_token = None

    token = _extract_refresh_token(request, body_token)

    refresh_service = RefreshTokenService(
        RefreshTokenRepository(db)
    )

    if token:

        await refresh_service.revoke_family(token)

    _clear_refresh_cookie(response)

    return MessageResponse(
        success=True,
        message="Logged out.",
    )
