"""
Database-backed session store for the Signal Session Manager.

Maps (our_device, remote_device, conversation) to a persisted
SignalSession row. The ratchet state is stored as JSON in the
`ratchet_state` column.
"""

import json
from uuid import UUID

from app.crypto.signal.double_ratchet import RatchetState
from app.crypto.signal.session import SessionStore
from app.models.signal_session import SessionState, SignalSession
from app.repositories.device_repository import DeviceRepository


class DBSessionStore(SessionStore):
    """
    Wraps the DeviceRepository to load/save ratchet state via the
    SignalSession model. Lookup keys are the DB primary key UUIDs
    of the devices/conversation.
    """

    def __init__(self, repository: DeviceRepository):
        self.repository = repository

    async def get(
        self,
        our_device_pk: UUID,
        remote_device_pk: UUID,
        conversation_pk: UUID,
    ) -> RatchetState | None:
        row = await self.repository.get_session(
            our_device_pk, remote_device_pk, conversation_pk
        )
        if row is None:
            return None
        try:
            return RatchetState.from_dict(json.loads(row.ratchet_state))
        except (json.JSONDecodeError, KeyError):
            return None

    async def save(
        self,
        our_device_pk: UUID,
        remote_device_pk: UUID,
        conversation_pk: UUID,
        state: RatchetState,
    ) -> None:
        data = json.dumps(state.to_dict())
        row = await self.repository.get_session(
            our_device_pk, remote_device_pk, conversation_pk
        )
        if row is None:
            row = SignalSession(
                device_id=our_device_pk,
                remote_device_id=remote_device_pk,
                conversation_id=conversation_pk,
                remote_identity_key="",
                our_identity_key="",
                root_key="",
                our_ratchet_key_private="",
                our_ratchet_key_public="",
                ratchet_state=data,
                state=SessionState.ACTIVE.value,
            )
            await self.repository.create_session(row)
        else:
            row.ratchet_state = data
            await self.repository.save_session(row)

    async def delete(
        self,
        our_device_pk: UUID,
        remote_device_pk: UUID,
        conversation_pk: UUID,
    ) -> None:
        row = await self.repository.get_session(
            our_device_pk, remote_device_pk, conversation_pk
        )
        if row is None:
            return
        await self.repository.delete(row)
        await self.repository.commit()
