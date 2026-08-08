from pydantic import BaseModel, Field


# ==========================================================
# Device Registration
# ==========================================================

class OneTimePreKeyUpload(BaseModel):
    key_id: int
    public_key: str
    private_key_encrypted: str


class RegisterDeviceRequest(BaseModel):
    device_id: str = Field(min_length=8, max_length=64)
    platform: str = "other"
    device_name: str | None = None
    platform_version: str | None = None
    app_version: str | None = None

    identity_key_public: str
    identity_key_x25519: str
    identity_key_private_encrypted: str

    signed_prekey_public: str
    signed_prekey_private_encrypted: str
    signed_prekey_id: int
    signed_prekey_signature: str

    one_time_prekeys: list[OneTimePreKeyUpload] = []


class RegisterDeviceResponse(BaseModel):
    success: bool = True
    device_id: str
    is_primary: bool


# ==========================================================
# Key Bundle (what a client fetches to initiate X3DH)
# ==========================================================

class SignedPreKeyBundle(BaseModel):
    key_id: int
    public_key: str
    signature: str


class OneTimePreKeyBundle(BaseModel):
    key_id: int
    public_key: str


class DeviceBundle(BaseModel):
    device_id: str
    identity_key: str
    x25519_identity_key: str
    signed_prekey: SignedPreKeyBundle
    one_time_prekeys: list[OneTimePreKeyBundle] = []


class KeyBundleResponse(BaseModel):
    user_id: str
    devices: list[DeviceBundle]


# ==========================================================
# One-Time PreKey replenishment
# ==========================================================

class ReplenishPreKeysResponse(BaseModel):
    success: bool = True
    one_time_prekeys: list[OneTimePreKeyUpload]


# ==========================================================
# One-Time PreKey upload (client-generated)
# ==========================================================

class UploadPreKeysRequest(BaseModel):
    device_id: str
    one_time_prekeys: list[OneTimePreKeyUpload] = []


# ==========================================================
# Device list / removal
# ==========================================================

class DeviceInfo(BaseModel):
    device_id: str
    device_name: str | None = None
    platform: str
    is_primary: bool
    is_active: bool
    last_seen: str | None = None
    created_at: str | None = None


class DeviceListResponse(BaseModel):
    devices: list[DeviceInfo]


class DeviceActionResponse(BaseModel):
    success: bool = True
    message: str