from uuid import UUID

from app.models.device import (
    Device,
    SignedPreKey,
    OneTimePreKey,
)
from app.models.user import User
from app.repositories.device_repository import DeviceRepository
from app.services.encryption_service import EncryptionService
from app.crypto.signal.primitives import (
    b64encode,
    b64decode,
    x25519_private_to_bytes,
    x25519_public_to_bytes,
)
from app.crypto.signal.x3dh import generate_x25519_keypair


# Default number of one-time prekeys to keep available
ONE_TIME_PREKEY_TARGET = 100


class DeviceService:
    """
    Manages devices and their Signal Protocol key material.

    Key generation happens on the client; the server stores the PUBLIC
    key material and the ENCRYPTED private key material (Fernet with
    MASTER_KEY) so it can complete X3DH responder steps on behalf of
    a device that is offline.
    """

    def __init__(self, repository: DeviceRepository):
        self.repository = repository

    # ==========================================================
    # Device Registration
    # ==========================================================

    async def register_device(
        self,
        user: User,
        *,
        device_id: str,
        platform: str = "other",
        device_name: str | None = None,
        platform_version: str | None = None,
        app_version: str | None = None,
        identity_key_public: str,                # b64 Ed25519 public
        identity_key_x25519: str,                # b64 X25519 public
        identity_key_private_encrypted: str,     # b64 Fernet(Ed25519 priv)
        signed_prekey_public: str,               # b64 X25519 public
        signed_prekey_private_encrypted: str,    # b64 Fernet(X25519 priv)
        signed_prekey_id: int,
        signed_prekey_signature: str,            # b64 Ed25519 sig
        one_time_prekeys: list[dict],            # [{key_id, public_key, private_key_encrypted}]
    ) -> Device:
        """Register (or re-register) a device with its key material."""

        existing = await self.repository.get_by_device_id(device_id)
        if existing is not None:
            existing.identity_key_public = identity_key_public
            existing.identity_key_x25519 = identity_key_x25519
            existing.identity_key_private_encrypted = identity_key_private_encrypted
            existing.is_active = True
            existing.platform = platform
            existing.device_name = device_name
            existing.app_version = app_version
            existing.unregistered_at = None
            device = existing
            await self.repository.update()
        else:
            is_first = (await self.repository.count_active_devices(user.id)) == 0
            device = Device(
                user_id=user.id,
                device_id=device_id,
                platform=platform,
                device_name=device_name,
                platform_version=platform_version,
                app_version=app_version,
                is_primary=is_first,
                is_active=True,
                identity_key_public=identity_key_public,
                identity_key_x25519=identity_key_x25519,
                identity_key_private_encrypted=identity_key_private_encrypted,
            )
            await self.repository.create_device(device)

        # Signed prekey (the latest id from the client replaces the old one)
        existing_spk = await self.repository.get_signed_prekey(
            device.id, signed_prekey_id
        )
        if existing_spk is None:
            await self.repository.create_signed_prekey(
                SignedPreKey(
                    device_id=device.id,
                    key_id=signed_prekey_id,
                    public_key=signed_prekey_public,
                    private_key_encrypted=signed_prekey_private_encrypted,
                    signature=signed_prekey_signature,
                )
            )

        # One-time prekeys (batch upload)
        for opk in one_time_prekeys:
            await self.repository.create_one_time_prekey(
                OneTimePreKey(
                    device_id=device.id,
                    key_id=opk["key_id"],
                    public_key=opk["public_key"],
                    private_key_encrypted=opk["private_key_encrypted"],
                )
            )

        await self.repository.commit()
        await self.repository.refresh(device)
        return device

    # ==========================================================
    # One-Time PreKey upload (client-generated batch)
    # ==========================================================

    async def upload_one_time_prekeys(
        self,
        device: Device,
        one_time_prekeys: list[dict],
    ) -> list[dict]:
        """
        Append a client-generated batch of one-time prekeys to an
        existing device.

        The client (not the server) generates and holds the private
        halves; the server only stores the public payload so other
        peers can initiate X3DH handshakes with this device.
        Duplicate key_ids are skipped (upload is idempotent).
        """
        stored = []
        for opk in one_time_prekeys:
            existing = await self.repository.get_one_time_prekey(
                device.id, opk["key_id"]
            )
            if existing is not None:
                continue
            row = OneTimePreKey(
                device_id=device.id,
                key_id=opk["key_id"],
                public_key=opk["public_key"],
                private_key_encrypted=opk["private_key_encrypted"],
            )
            await self.repository.create_one_time_prekey(row)
            stored.append(row)

        await self.repository.commit()
        return stored

    # ==========================================================
    # Key Bundle serving (used by X3DH initiators)
    # ==========================================================

    async def get_device_bundle(
        self,
        user_id: UUID,
    ) -> dict:
        """
        Return a key bundle for ALL active devices of a user, ready for
        X3DH initiation.
        """
        devices = await self.repository.get_by_user_id(user_id)
        if not devices:
            return {"user_id": str(user_id), "devices": []}

        devices_data = []
        for device in devices:
            spks = await self.repository.get_active_signed_prekeys(device.id)
            if not spks:
                continue
            spk = spks[0]

            opks = await self.repository.get_unconsumed_one_time_prekeys(
                device.id, limit=1
            )
            opk_data = None
            if opks:
                opk_data = {
                    "key_id": opks[0].key_id,
                    "public_key": opks[0].public_key,
                }

            devices_data.append({
                "device_id": device.device_id,
                "identity_key": device.identity_key_public,
                "x25519_identity_key": device.identity_key_x25519,
                "signed_prekey": {
                    "key_id": spk.key_id,
                    "public_key": spk.public_key,
                    "signature": spk.signature,
                },
                "one_time_prekeys": [opk_data] if opk_data else [],
            })

        return {"user_id": str(user_id), "devices": devices_data}

    # ===========================================================
    # One-Time PreKey replenishment
    # ===========================================================

    async def replenish_one_time_prekeys(
        self,
        device: Device,
    ) -> list[dict]:
        """
        Top the device's unconsumed OPK supply back to the target and
        return the newly generated prekeys (with encrypted private keys)
        so the client can keep them in its secure local store.
        """
        opks = await self.repository.get_unconsumed_one_time_prekeys(
            device.id, limit=ONE_TIME_PREKEY_TARGET
        )
        current_count = len(opks)
        if current_count >= ONE_TIME_PREKEY_TARGET:
            return []

        needed = ONE_TIME_PREKEY_TARGET - current_count
        next_id = await self.repository.get_next_one_time_prekey_id(device.id)

        generated = []
        for _ in range(needed):
            priv, pub = generate_x25519_keypair()
            priv_bytes = x25519_private_to_bytes(priv)
            pub_bytes = x25519_public_to_bytes(pub)

            encrypted_private = b64encode(
                EncryptionService.get_fernet().encrypt(priv_bytes)
            )

            row = OneTimePreKey(
                device_id=device.id,
                key_id=next_id,
                public_key=b64encode(pub_bytes),
                private_key_encrypted=encrypted_private,
            )
            await self.repository.create_one_time_prekey(row)

            generated.append({
                "key_id": next_id,
                "public_key": b64encode(pub_bytes),
                "private_key_encrypted": encrypted_private,
            })
            next_id += 1

        await self.repository.commit()
        return generated

    async def replenish_one_time_prekeys_for_user(
        self,
        user_id: UUID,
    ) -> list[dict]:
        """Replenish all active devices of a user."""
        devices = await self.repository.get_by_user_id(user_id)
        total = []
        for device in devices:
            total.extend(await self.replenish_one_time_prekeys(device))
        return total

    # ================================================================
    # Consume a one-time prekey (after successful X3DH as responder)
    # ================================================================

    async def consume_one_time_prekey(
        self,
        device: Device,
        key_id: int,
        consumed_by_device_pk: UUID,
    ):
        opk = await self.repository.get_one_time_prekey(
            device.id, key_id
        )
        if opk is None or opk.consumed:
            return
        await self.repository.mark_one_time_prekey_consumed(
            opk.id, consumed_by_device_pk
        )
        await self.repository.commit()

    # ================================================================
    # Helpers
    # ================================================================

    @staticmethod
    def encrypt_key(raw: bytes) -> str:
        """Encrypt private key material with the server master key."""
        return b64encode(EncryptionService.get_fernet().encrypt(raw))

    @staticmethod
    def decrypt_key(encrypted_b64: str) -> bytes:
        return EncryptionService.get_fernet().decrypt(
            b64decode(encrypted_b64)
        )

    async def get_device_signed_prekey_with_private(
        self,
        device: Device,
        key_id: int,
    ):
        """Fetch a signed prekey row plus its decrypted private bytes."""
        spk = await self.repository.get_signed_prekey(device.id, key_id)
        if spk is None:
            return None
        return {
            "key_id": spk.key_id,
            "public_key": spk.public_key,
            "private_key": self.decrypt_key(spk.private_key_encrypted),
        }

    async def get_device_one_time_prekey_with_private(
        self,
        device: Device,
        key_id: int,
    ):
        """Fetch an OPK row plus its decrypted private bytes."""
        opk = await self.repository.get_one_time_prekey(device.id, key_id)
        if opk is None:
            return None
        return {
            "key_id": opk.key_id,
            "public_key": opk.public_key,
            "private_key": self.decrypt_key(opk.private_key_encrypted),
        }