from uuid import UUID

from pydantic import BaseModel


class UploadPublicKeyRequest(BaseModel):
    public_key: str


class PublicKeyResponse(BaseModel):
    user_id: UUID
    public_key: str | None