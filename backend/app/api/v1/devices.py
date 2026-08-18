from uuid import UUID

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.database.session import get_db
from app.dependencies.auth import get_current_user

from app.models.user import User
from app.repositories.device_repository import DeviceRepository
from app.services.device_service import DeviceService
from app.services.email_service import EmailService
from app.services.recovery_service import create_recovery_key

from app.schemas.device import (
    RegisterDeviceRequest,
    RegisterDeviceResponse,
    KeyBundleResponse,
    ReplenishPreKeysResponse,
    UploadPreKeysRequest,
    DeviceListResponse,
    DeviceActionResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/devices",
    tags=["Devices"],
)


# ==========================================================
# Register Device (with Signal Protocol key material)
# ==========================================================

@router.post(
    "/register",
    response_model=RegisterDeviceResponse,
)
async def register_device(
    request: RegisterDeviceRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    repository = DeviceRepository(db)
    service = DeviceService(repository)

    device = await service.register_device(
        user=current_user,
        device_id=request.device_id,
        platform=request.platform,
        device_name=request.device_name,
        platform_version=request.platform_version,
        app_version=request.app_version,
        identity_key_public=request.identity_key_public,
        identity_key_x25519=request.identity_key_x25519,
        identity_key_private_encrypted=request.identity_key_private_encrypted,
        signed_prekey_public=request.signed_prekey_public,
        signed_prekey_private_encrypted=request.signed_prekey_private_encrypted,
        signed_prekey_id=request.signed_prekey_id,
        signed_prekey_signature=request.signed_prekey_signature,
        one_time_prekeys=[
            {
                "key_id": opk.key_id,
                "public_key": opk.public_key,
                "private_key_encrypted": opk.private_key_encrypted,
            }
            for opk in request.one_time_prekeys
        ],
    )

    # ==========================================================
    # Account recovery key (created exactly once per account)
    #
    # A fresh browser has no way to decrypt history that predates
    # its registration — unless the account keeps a sync secret
    # wrapped by a one-time recovery code. Created on the first
    # registration that finds none; the code is returned exactly
    # once (shown on screen + emailed), never stored.
    # ==========================================================

    recovery = None

    # Load the user row in THIS session (the dependency-injected
    # instance may belong to another session) and create the
    # recovery key exactly once per account.
    user_row = (
        await db.execute(
            select(User).where(User.id == current_user.id)
        )
    ).scalar_one_or_none()

    if user_row is not None and user_row.recovery_wrapped_key is None:

        recovery = create_recovery_key()

        user_row.recovery_salt = recovery["salt"]
        user_row.recovery_wrapped_key = recovery["wrapped_key"]

        await db.commit()

        logger.info(
            "Recovery key created for user %s (code sent once)",
            user_row.id,
        )

        if settings.DEBUG and settings.APP_ENV == "development":

            logger.warning(
                "[DEV] Recovery code for %s: %s",
                user_row.email,
                recovery["code_display"],
            )

        try:

            await EmailService().send_recovery_code_email(
                recipient_email=user_row.email,
                code=recovery["code"],
            )

        except Exception as exc:

            # The code is shown on screen too — mail is best-effort.
            logger.warning(
                "Recovery code email failed for %s: %s",
                current_user.email,
                exc,
            )

    return RegisterDeviceResponse(
        device_id=device.device_id,
        is_primary=device.is_primary,
        recovery_code=recovery["code_display"] if recovery else None,
        recovery_salt=recovery["salt"] if recovery else None,
        recovery_wrapped_key=recovery["wrapped_key"] if recovery else None,
    )


# ==========================================================
# Fetch Key Bundle (for X3DH initiation)
# ==========================================================

@router.get(
    "/{user_id}/bundle",
    response_model=KeyBundleResponse,
)
async def get_key_bundle(
    user_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    repository = DeviceRepository(db)
    service = DeviceService(repository)

    bundle = await service.get_device_bundle(user_id)

    if not bundle["devices"]:
        raise HTTPException(
            status_code=404,
            detail="No devices registered for this user.",
        )

    return bundle


# ==========================================================
# Replenish One-Time PreKeys
# ==========================================================

@router.post(
    "/prekeys/replenish",
    response_model=ReplenishPreKeysResponse,
)
async def replenish_prekeys(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    repository = DeviceRepository(db)
    service = DeviceService(repository)

    device = await repository.get_primary_device(current_user.id)
    if device is None:
        raise HTTPException(
            status_code=404,
            detail="No registered device found."
        )

    generated = await service.replenish_one_time_prekeys(device)

    return ReplenishPreKeysResponse(
        one_time_prekeys=generated
    )


# ==========================================================
# Upload Client-Generated One-Time PreKeys
# ==========================================================

@router.post(
    "/prekeys/upload",
    response_model=ReplenishPreKeysResponse,
)
async def upload_prekeys(
    request: UploadPreKeysRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    repository = DeviceRepository(db)
    service = DeviceService(repository)

    device = await repository.get_by_device_id(request.device_id)
    if device is None or device.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Device not found.")
    if not device.is_active:
        raise HTTPException(status_code=400, detail="Device is inactive.")

    stored = await service.upload_one_time_prekeys(
        device,
        [
            {
                "key_id": opk.key_id,
                "public_key": opk.public_key,
                "private_key_encrypted": opk.private_key_encrypted,
            }
            for opk in request.one_time_prekeys
        ],
    )

    return ReplenishPreKeysResponse(
        one_time_prekeys=[
            {
                "key_id": row.key_id,
                "public_key": row.public_key,
                "private_key_encrypted": row.private_key_encrypted,
            }
            for row in stored
        ]
    )


# ==========================================================
# List Devices
# ==========================================================

@router.get(
    "/me",
    response_model=DeviceListResponse,
)
async def list_devices(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    repository = DeviceRepository(db)
    devices = await repository.get_by_user_id(current_user.id)

    return DeviceListResponse(
        devices=[
            {
                "device_id": d.device_id,
                "device_name": d.device_name,
                "platform": d.platform,
                "is_primary": d.is_primary,
                "is_active": d.is_active,
                "last_seen": d.last_seen.isoformat() if d.last_seen else None,
                "created_at": d.registered_at.isoformat() if d.registered_at else None,
            }
            for d in devices
        ]
    )


# ==========================================================
# Remove Device
# ==========================================================

@router.delete(
    "/{device_id}",
    response_model=DeviceActionResponse,
)
async def remove_device(
    device_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    repository = DeviceRepository(db)
    device = await repository.get_by_device_id(device_id)

    if device is None or device.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Device not found.")
    if device.is_primary:
        raise HTTPException(
            status_code=400,
            detail="Cannot remove the primary device.",
        )

    await repository.disable_device(device.id)
    await repository.commit()

    return DeviceActionResponse(
        message="Device removed.",
    )