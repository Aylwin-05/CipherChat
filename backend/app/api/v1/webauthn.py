import base64
import json
import logging
import time
import uuid

from app.core.config import settings
from app.database.session import get_db
from app.dependencies.auth import get_current_user
from app.dependencies.rate_limit import rate_limit
from app.models.webauthn_credential import WebauthnCredential
from app.repositories.auth_repository import AuthRepository
from app.repositories.refresh_token_repository import (
    RefreshTokenRepository,
)
from app.repositories.webauthn_repository import (
    WebAuthnRepository,
)
from app.services.jwt_service import JWTService
from app.services.refresh_token_service import RefreshTokenService
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
    Response,
)
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/webauthn",
    tags=["WebAuthn"],
)

# ==========================================================
# In-memory challenge store (TTL 5 min)
# ==========================================================

_CHALLENGE_TTL = 300

_pending_challenges: dict[str, dict] = {}


def _store_challenge(key: str, data: dict):

    data["_exp"] = time.time() + _CHALLENGE_TTL

    _pending_challenges[key] = data


def _consume_challenge(key: str) -> dict | None:

    entry = _pending_challenges.pop(key, None)

    if entry is None:

        return None

    if time.time() > entry.get("_exp", 0):

        return None

    return entry


def _cleanup_stored_challenges():

    now = time.time()

    expired = [
        k for k, v in _pending_challenges.items()
        if now > v.get("_exp", 0)
    ]

    for k in expired:

        _pending_challenges.pop(k, None)


# ==========================================================
# Helpers
# ==========================================================

def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_decode(s: str) -> bytes:
    pad = 4 - len(s) % 4
    if pad != 4:
        s += "=" * pad
    return base64.urlsafe_b64decode(s)


def _generate_challenge() -> bytes:
    return uuid.uuid4().bytes + uuid.uuid4().bytes


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        candidate = forwarded.split(",")[0].strip()
        try:
            import ipaddress
            ipaddress.ip_address(candidate)
            return candidate
        except ValueError:
            pass
    return request.client.host if request.client else "unknown"


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


# ==========================================================
# Request / response schemas
# ==========================================================

class RegisterBeginRequest(BaseModel):
    device_name: str | None = None


class RegisterCompleteRequest(BaseModel):
    credential_id: str
    client_data_json: str
    attestation_object: str
    device_name: str | None = None


class LoginBeginRequest(BaseModel):
    email: str


class LoginCompleteRequest(BaseModel):
    credential_id: str
    client_data_json: str
    authenticator_data: str
    signature: str
    user_handle: str | None = None


class CredentialInfo(BaseModel):
    id: uuid.UUID
    credential_id: str
    device_name: str | None
    sign_count: int
    created_at: str
    last_used_at: str | None


# ==========================================================
# POST /webauthn/register/begin
# ==========================================================

@router.post(
    "/register/begin",
    dependencies=[
        rate_limit("webauthn.register.begin.ip", 20, 600),
    ],
)
async def register_begin(
    request_body: RegisterBeginRequest,
    request: Request,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):

    _cleanup_stored_challenges()

    challenge = _generate_challenge()

    user_handle = current_user.id.bytes

    challenge_key = _b64url_encode(challenge)

    _store_challenge(
        challenge_key,
        {
            "user_id": str(current_user.id),
            "email": current_user.email,
            "username": current_user.username,
            "device_name": request_body.device_name,
        },
    )

    credential_id = str(uuid.uuid4())

    _store_challenge(
        f"reg:{credential_id}",
        {
            "user_id": str(current_user.id),
            "challenge_b64": challenge_key,
            "device_name": request_body.device_name,
        },
    )

    return {
        "challenge": _b64url_encode(challenge),
        "rp": {
            "id": settings.WEBAUTHN_RP_ID,
            "name": settings.WEBAUTHN_RP_NAME,
        },
        "user": {
            "id": _b64url_encode(user_handle),
            "name": current_user.email,
            "displayName": current_user.display_name,
        },
        "pubKeyCredParams": [
            {"type": "public-key", "alg": -7},
            {"type": "public-key", "alg": -257},
        ],
        "timeout": 60000,
        "attestation": "none",
        "authenticatorSelection": {
            "residentKey": "preferred",
            "userVerification": "preferred",
        },
    }


# ==========================================================
# POST /webauthn/register/complete
# ==========================================================

@router.post(
    "/register/complete",
    dependencies=[
        rate_limit("webauthn.register.complete.ip", 20, 600),
    ],
)
async def register_complete(
    request_body: RegisterCompleteRequest,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):

    challenge_key = _b64url_decode(request_body.client_data_json)

    import hashlib as _hl

    client_hash = _hl.sha256(challenge_key).hexdigest()

    pending = _consume_challenge(client_hash)

    if pending is None:

        raise HTTPException(
            status_code=400,
            detail="Challenge expired or not found.",
        )

    repository = WebAuthnRepository(db)

    existing = await repository.get_by_credential_id(
        request_body.credential_id,
    )

    if existing is not None:

        raise HTTPException(
            status_code=409,
            detail="Credential already registered.",
        )

    credential = WebauthnCredential(
        user_id=uuid.UUID(pending["user_id"]),
        credential_id=request_body.credential_id,
        public_key=json.dumps({
            "attestation_object": request_body.attestation_object,
            "client_data_json": request_body.client_data_json,
        }),
        sign_count=0,
        device_name=pending.get("device_name"),
    )

    await repository.create_credential(credential)

    await db.commit()

    logger.info(
        "WebAuthn credential registered: user=%s cred=%s",
        pending["user_id"],
        request_body.credential_id,
    )

    return {"success": True}


# ==========================================================
# POST /webauthn/login/begin
# ==========================================================

@router.post(
    "/login/begin",
    dependencies=[
        rate_limit("webauthn.login.begin.ip", 20, 600),
    ],
)
async def login_begin(
    request_body: LoginBeginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):

    _cleanup_stored_challenges()

    auth_repo = AuthRepository(db)

    user = await auth_repo.get_user_by_email(
        request_body.email,
    )

    if user is None:

        raise HTTPException(
            status_code=404,
            detail="No account found with that email.",
        )

    webauthn_repo = WebAuthnRepository(db)

    credentials = await webauthn_repo.get_by_user(user.id)

    if not credentials:

        raise HTTPException(
            status_code=404,
            detail="No passkeys registered for this account.",
        )

    challenge = _generate_challenge()

    challenge_b64 = _b64url_encode(challenge)

    _store_challenge(
        challenge_b64,
        {
            "user_id": str(user.id),
            "email": user.email,
        },
    )

    allow_credentials = [
        {
            "type": "public-key",
            "id": cred.credential_id,
        }
        for cred in credentials
    ]

    return {
        "challenge": challenge_b64,
        "rpId": settings.WEBAUTHN_RP_ID,
        "timeout": 60000,
        "userVerification": "preferred",
        "allowCredentials": allow_credentials,
    }


# ==========================================================
# POST /webauthn/login/complete
# ==========================================================

@router.post(
    "/login/complete",
    dependencies=[
        rate_limit("webauthn.login.complete.ip", 20, 600),
    ],
)
async def login_complete(
    request: Request,
    response: Response,
    request_body: LoginCompleteRequest,
    db: AsyncSession = Depends(get_db),
):

    import hashlib as _hl

    client_hash = _hl.sha256(
        _b64url_decode(request_body.client_data_json)
    ).hexdigest()

    pending = _consume_challenge(client_hash)

    if pending is None:

        raise HTTPException(
            status_code=400,
            detail="Challenge expired or not found.",
        )

    repository = WebAuthnRepository(db)

    credential = await repository.get_by_credential_id(
        request_body.credential_id,
    )

    if credential is None:

        raise HTTPException(
            status_code=400,
            detail="Unknown credential.",
        )

    new_count = credential.sign_count + 1

    await repository.update_sign_count(
        credential,
        new_count,
    )

    await db.commit()

    auth_repo = AuthRepository(db)

    user = await auth_repo.get_user_by_id(credential.user_id)

    if user is None or not user.is_active:

        raise HTTPException(
            status_code=401,
            detail="Account not found or deactivated.",
        )

    jwt = JWTService()

    access_token = jwt.create_access_token(
        user_id=str(user.id),
        email=user.email,
    )

    refresh_service = RefreshTokenService(
        RefreshTokenRepository(db)
    )

    refresh_token = await refresh_service.issue(
        user.id,
        user_agent=request.headers.get("user-agent"),
        ip_address=_client_ip(request),
    )

    _set_refresh_cookie(response, refresh_token)

    logger.info(
        "WebAuthn login: user=%s cred=%s",
        user.id,
        request_body.credential_id,
    )

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "Bearer",
        "user": {
            "id": str(user.id),
            "email": user.email,
            "username": user.username,
            "display_name": user.display_name,
        },
    }


# ==========================================================
# GET /webauthn/credentials
# ==========================================================

@router.get(
    "/credentials",
)
async def list_credentials(
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):

    repository = WebAuthnRepository(db)

    credentials = await repository.get_by_user(
        current_user.id,
    )

    return [
        CredentialInfo(
            id=cred.id,
            credential_id=cred.credential_id,
            device_name=cred.device_name,
            sign_count=cred.sign_count,
            created_at=cred.created_at.isoformat(),
            last_used_at=(
                cred.last_used_at.isoformat()
                if cred.last_used_at else None
            ),
        )
        for cred in credentials
    ]


# ==========================================================
# DELETE /webauthn/credentials/{credential_id}
# ==========================================================

@router.delete(
    "/credentials/{credential_id}",
    dependencies=[
        rate_limit("webauthn.credentials.delete.ip", 20, 600),
    ],
)
async def delete_credential(
    credential_id: uuid.UUID,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):

    repository = WebAuthnRepository(db)

    credentials = await repository.get_by_user(
        current_user.id,
    )

    target = next(
        (c for c in credentials if c.id == credential_id),
        None,
    )

    if target is None:

        raise HTTPException(
            status_code=404,
            detail="Credential not found.",
        )

    await repository.delete_credential(target)

    await db.commit()

    return {"success": True}
