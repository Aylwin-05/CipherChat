from pydantic import BaseModel


# ==========================================================
# Upload Public Key
# ==========================================================

class UploadPublicKeyRequest(BaseModel):
    public_key: str


# ==========================================================
# Public Key Response
# ==========================================================

class PublicKeyResponse(BaseModel):
    public_key: str


# ==========================================================
# Generic Response
# ==========================================================

class KeyUploadResponse(BaseModel):
    success: bool
    message: str