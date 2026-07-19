from uuid import UUID

from app.websocket.manager import manager


class PresenceService:
    """
    Handles user online/offline presence.
    """

    async def user_connected(
        self,
        conversation_id: UUID,
        user_id: UUID,
    ):

        await manager.broadcast(
            conversation_id,
            {
                "event": "presence",
                "data": {
                    "user_id": str(user_id),
                    "status": "online",
                },
            },
        )

    async def user_disconnected(
        self,
        conversation_id: UUID,
        user_id: UUID,
    ):

        await manager.broadcast(
            conversation_id,
            {
                "event": "presence",
                "data": {
                    "user_id": str(user_id),
                    "status": "offline",
                },
            },
        )