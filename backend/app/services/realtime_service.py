from uuid import UUID

from app.models.user import User
from app.services.presence_service import PresenceService
from app.services.websocket_service import WebSocketService
from app.websocket.manager import manager


class RealtimeService:
    """
    Coordinates all realtime websocket features.

    This service is responsible only for realtime
    websocket events.

    Business logic remains inside dedicated services.
    """

    def __init__(
        self,
        websocket_service: WebSocketService,
    ):
        self.websocket_service = websocket_service
        self.presence_service = PresenceService()

    # ==========================================================
    # Message
    # ==========================================================

    async def message(
        self,
        conversation_id: UUID,
        current_user: User,
        content: str,
    ):
        return await self.websocket_service.handle_message(
            conversation_id,
            current_user,
            content,
        )

    # ==========================================================
    # Presence
    # ==========================================================

    async def user_connected(
        self,
        conversation_id: UUID,
        current_user: User,
    ):
        await self.presence_service.user_connected(
            conversation_id,
            current_user.id,
        )

    async def user_disconnected(
        self,
        conversation_id: UUID,
        current_user: User,
    ):
        await self.presence_service.user_disconnected(
            conversation_id,
            current_user.id,
        )

    # ==========================================================
    # Typing
    # ==========================================================

    async def typing(
        self,
        conversation_id: UUID,
        current_user: User,
    ):
        await manager.broadcast(
            conversation_id,
            {
                "event": "typing",
                "data": {
                    "user_id": str(current_user.id),
                },
            },
        )

    async def stop_typing(
        self,
        conversation_id: UUID,
        current_user: User,
    ):
        await manager.broadcast(
            conversation_id,
            {
                "event": "stop_typing",
                "data": {
                    "user_id": str(current_user.id),
                },
            },
        )

    # ==========================================================
    # Delivery Receipts
    # ==========================================================

    async def delivered(
        self,
        conversation_id: UUID,
        current_user: User,
        message,
    ):
        """
        Broadcast a delivered receipt.

        The message should already be marked as delivered
        by the MessageService before calling this method.
        """

        await manager.broadcast(
            conversation_id,
            {
                "event": "delivered",
                "data": {
                    "message_id": str(message.id),
                    "user_id": str(current_user.id),
                    "delivered_at": (
                        message.delivered_at.isoformat()
                        if message.delivered_at
                        else None
                    ),
                },
            },
        )

    # ==========================================================
    # Read Receipts
    # ==========================================================

    async def read(
        self,
        conversation_id: UUID,
        current_user: User,
        message,
    ):
        """
        Broadcast a read receipt.

        The message should already be marked as read
        by the MessageService before calling this method.
        """

        await manager.broadcast(
            conversation_id,
            {
                "event": "read",
                "data": {
                    "message_id": str(message.id),
                    "user_id": str(current_user.id),
                    "read_at": (
                        message.read_at.isoformat()
                        if message.read_at
                        else None
                    ),
                },
            },
        )