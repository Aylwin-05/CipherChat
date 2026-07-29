from pydantic import BaseModel

class UploadPublicKeyRequest(BaseModel):
    public_key: str


class PublicKeyResponse(BaseModel):
    user_id: str
    public_key: str
class RegisterKeysRequest(BaseModel):
    """
    Public cryptographic keys uploaded by the client.
    """

    public_key: str

    signed_prekey: str

    signed_prekey_signature: str