from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db
from app.dependencies.auth import get_current_user

from app.models.device import Device
from app.models.user import User

from app.repositories.device_repository import (
    DeviceRepository,
)

from app.schemas.device import (
    DeviceActionResponse,
    DeviceInfo,
    DeviceListResponse,
    KeyBundleResponse,
    RegisterDeviceRequest,
    RegisterDeviceResponse,
    ReplenishPreKeysResponse,
    UploadPreKeysRequest,
)

from app.services.device_service import (
    DeviceService,
)

router = APIRouter(prefix="/devices", tags=["devices"])


# ==========================================================
# Helpers
# ==========================================================

def _service(db: AsyncSession) -> DeviceService:
    return DeviceService(DeviceRepository(db))


def _device_info(device: Device) -> DeviceInfo:
    return DeviceInfo(
        device_id=device.device_id,
        device_name=device.device_name,
        platform=device.platform,
        is_primary=device.is_primary,
        is_active=device.is_active,
        last_seen=(
            device.last_seen.isoformat()
            if device.last_seen
            else None
        ),
        created_at=device.registered_at.isoformat()
        if device.registered_at
        else None,
    )


# ==========================================================
# Register Device (public key material only)
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

    service = _service(db)

    try:

        device, recovery_info = await service.register_device(
            current_user,
            device_id=request.device_id,
            platform=request.platform,
            device_name=request.device_name,
            platform_version=request.platform_version,
            app_version=request.app_version,
            identity_key_public=request.identity_key_public,
            identity_key_x25519=request.identity_key_x25519,
            signed_prekey_public=request.signed_prekey_public,
            signed_prekey_id=request.signed_prekey_id,
            signed_prekey_signature=request.signed_prekey_signature,
            one_time_prekeys=[
                opk.model_dump()
                for opk in request.one_time_prekeys
            ],
        )

    except PermissionError as e:
        raise HTTPException(
            status_code=403,
            detail=str(e),
        )

    await db.commit()

    response = {
        "success": True,
        "device_id": device.device_id,
        "is_primary": device.is_primary,
    }

    # Exactly-once payload: only the registration that MINTED the
    # recovery key carries the plaintext code.
    if recovery_info is not None:
        response.update(
            {
                "recovery_code": recovery_info["code"],
                "recovery_salt": recovery_info["salt"],
                "recovery_wrapped_key": recovery_info["wrapped_key"],
            }
        )

    return response


# ==========================================================
# Key Bundle (for X3DH initiators)
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

    service = _service(db)

    bundle = await service.get_device_bundle(user_id)

    if not bundle["devices"]:
        raise HTTPException(
            status_code=404,
            detail="No registered devices found for this user.",
        )

    return bundle


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

    device = await repository.get_by_device_id(
        request.device_id
    )

    if device is None:
        raise HTTPException(
            status_code=404,
            detail="Device not found.",
        )

    if device.user_id != current_user.id:
        raise HTTPException(
            status_code=403,
            detail="This device belongs to another account.",
        )

    service = _service(db)

    stored = await service.upload_one_time_prekeys(
        device,
        [
            opk.model_dump()
            for opk in request.one_time_prekeys
        ],
    )

    return {
        "success": True,
        "one_time_prekeys": [
            {
                "key_id": row.key_id,
                "public_key": row.public_key,
            }
            for row in stored
        ],
    }


# ==========================================================
# List My Devices
# ==========================================================

@router.get(
    "/me",
    response_model=DeviceListResponse,
)
async def list_my_devices(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):

    repository = DeviceRepository(db)

    devices = await repository.get_by_user_id(
        current_user.id
    )

    return {
        "devices": [
            _device_info(device)
            for device in devices
        ]
    }


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

    device = await repository.get_by_device_id(
        device_id
    )

    if device is None or device.user_id != current_user.id:
        raise HTTPException(
            status_code=404,
            detail="Device not found.",
        )

    if device.is_primary:
        raise HTTPException(
            status_code=400,
            detail="The primary device cannot be removed.",
        )

    # Wipe key material so a future re-registration starts
    # from an empty prekey pool, then deactivate the record.
    await repository.delete_device_prekeys(device.id)

    await repository.disable_device(device.id)

    await repository.commit()

    return {
        "success": True,
        "message": f"Device {device_id} removed.",
    }
