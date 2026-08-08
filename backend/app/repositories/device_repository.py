from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.device import Device, SignedPreKey, OneTimePreKey
from app.models.signal_session import SignalSession
from app.repositories.base_repository import BaseRepository


class DeviceRepository(BaseRepository):
    """
    Repository responsible for Device, SignedPreKey, OneTimePreKey and
    SignalSession operations.
    """

    # ==========================================================
    # Devices
    # ==========================================================

    async def create_device(
        self,
        device: Device,
    ) -> Device:
        return await self.create(device)

    async def get_by_device_id(
        self,
        device_id: str,
    ) -> Device | None:
        result = await self.execute(
            select(Device).where(
                Device.device_id == device_id
            )
        )
        return result.scalar_one_or_none()

    async def get_by_id(
        self,
        device_pk: UUID,
    ) -> Device | None:
        result = await self.execute(
            select(Device).where(
                Device.id == device_pk
            )
        )
        return result.scalar_one_or_none()

    async def get_by_user_id(
        self,
        user_id: UUID,
    ) -> list[Device]:
        result = await self.execute(
            select(Device).where(
                Device.user_id == user_id,
                Device.is_active.is_(True),
            ).order_by(Device.is_primary.desc(), Device.registered_at)
        )
        return list(result.scalars().all())

    async def get_active_device_ids(
        self,
        user_id: UUID,
    ) -> list[str]:
        result = await self.execute(
            select(Device.device_id).where(
                Device.user_id == user_id,
                Device.is_active.is_(True),
            )
        )
        return list(result.scalars().all())

    async def get_primary_device(
        self,
        user_id: UUID,
    ) -> Device | None:
        result = await self.execute(
            select(Device).where(
                Device.user_id == user_id,
                Device.is_primary.is_(True),
                Device.is_active.is_(True),
            )
        )
        return result.scalar_one_or_none()

    async def set_primary(
        self,
        user_id: UUID,
        device_pk: UUID,
    ):
        # Demote all of the user's devices first
        await self.db.execute(
            update(Device)
            .where(Device.user_id == user_id)
            .values(is_primary=False)
            .execution_options(synchronize_session=False)
        )
        # Promote the target device
        await self.db.execute(
            update(Device)
            .where(Device.id == device_pk)
            .values(is_primary=True)
            .execution_options(synchronize_session=False)
        )

    async def disable_device(
        self,
        device_pk: UUID,
    ):
        await self.db.execute(
            update(Device)
            .where(Device.id == device_pk)
            .values(is_active=False)
            .execution_options(synchronize_session=False)
        )

    async def count_active_devices(
        self,
        user_id: UUID,
    ) -> int:
        result = await self.execute(
            select(Device).where(
                Device.user_id == user_id,
                Device.is_active.is_(True),
            )
        )
        return len(result.scalars().all())

    # ==========================================================
    # Signed PreKeys
    # ==========================================================

    async def create_signed_prekey(
        self,
        prekey: SignedPreKey,
    ) -> SignedPreKey:
        return await self.create(prekey)

    async def get_active_signed_prekeys(
        self,
        device_pk: UUID,
    ) -> list[SignedPreKey]:
        result = await self.execute(
            select(SignedPreKey).where(
                SignedPreKey.device_id == device_pk,
            ).order_by(SignedPreKey.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_signed_prekey(
        self,
        device_pk: UUID,
        key_id: int,
    ) -> SignedPreKey | None:
        result = await self.execute(
            select(SignedPreKey).where(
                SignedPreKey.device_id == device_pk,
                SignedPreKey.key_id == key_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_next_signed_prekey_id(
        self,
        device_pk: UUID,
    ) -> int:
        result = await self.execute(
            select(SignedPreKey.key_id).where(
                SignedPreKey.device_id == device_pk,
            ).order_by(SignedPreKey.key_id.desc()).limit(1)
        )
        latest = result.scalar_one_or_none()
        return (latest or 0) + 1

    # ===========================================================
    # One-Time PreKeys
    # ===========================================================

    async def create_one_time_prekey(
        self,
        prekey: OneTimePreKey,
    ) -> OneTimePreKey:
        return await self.create(prekey)

    async def get_unconsumed_one_time_prekeys(
        self,
        device_pk: UUID,
        limit: int = 100,
    ) -> list[OneTimePreKey]:
        result = await self.execute(
            select(OneTimePreKey).where(
                OneTimePreKey.device_id == device_pk,
                OneTimePreKey.consumed.is_(False),
            ).order_by(OneTimePreKey.key_id).limit(limit)
        )
        return list(result.scalars().all())

    async def get_one_time_prekey(
        self,
        device_pk: UUID,
        key_id: int,
    ) -> OneTimePreKey | None:
        result = await self.execute(
            select(OneTimePreKey).where(
                OneTimePreKey.device_id == device_pk,
                OneTimePreKey.key_id == key_id,
            )
        )
        return result.scalar_one_or_none()

    async def mark_one_time_prekey_consumed(
        self,
        prekey_pk: UUID,
        consumed_by_device_pk: UUID | None = None,
    ):
        from datetime import datetime, timezone
        await self.db.execute(
            update(OneTimePreKey)
            .where(OneTimePreKey.id == prekey_pk)
            .values(
                consumed=True,
                consumed_at=datetime.now(timezone.utc),
                consumed_by_device_id=consumed_by_device_pk,
            )
            .execution_options(synchronize_session=False)
        )

    async def get_next_one_time_prekey_id(
        self,
        device_pk: UUID,
    ) -> int:
        result = await self.execute(
            select(OneTimePreKey.key_id).where(
                OneTimePreKey.device_id == device_pk,
            ).order_by(OneTimePreKey.key_id.desc()).limit(1)
        )
        latest = result.scalar_one_or_none()
        return (latest or 0) + 1

    # ===========================================================
    # Signal Sessions
    # ===========================================================

    async def get_session(
        self,
        our_device_pk: UUID,
        remote_device_pk: UUID,
        conversation_pk: UUID,
    ) -> SignalSession | None:
        result = await self.execute(
            select(SignalSession).where(
                SignalSession.device_id == our_device_pk,
                SignalSession.remote_device_id == remote_device_pk,
                SignalSession.conversation_id == conversation_pk,
            )
        )
        return result.scalar_one_or_none()

    async def create_session(
        self,
        session: SignalSession,
    ) -> SignalSession:
        return await self.create(session)

    async def save_session(
        self,
        session: SignalSession,
    ) -> SignalSession:
        await self.update()
        await self.refresh(session)
        return session