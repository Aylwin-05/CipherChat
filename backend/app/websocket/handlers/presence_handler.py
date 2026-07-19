from uuid import UUID

from fastapi import WebSocket

from app.websocket.connection_manager import manager
from app.websocket.events import events


class PresenceHandler:
    """
    Handles all presence-related WebSocket events.

    Responsibilities:
    - Connect user
    - Disconnect user
    - Typing indicators
    - Ping/Pong

    This class never talks to the database.
    """

    # ==========================================================
    # Connect
    # ==========================================================

    async def connect(
        self,
        conversation_id: UUID,
        user_id: UUID,
        websocket: WebSocket,
    ):
        await manager.connect(
            conversation_id,
            user_id,
            websocket,
        )

        await events.connected(
            websocket,
            user_id,
            conversation_id,
        )

    # ==========================================================
    # Disconnect
    # ==========================================================

    async def disconnect(
        self,
        conversation_id: UUID,
        user_id: UUID,
        websocket: WebSocket,
    ):
        manager.disconnect(
            conversation_id,
            user_id,
            websocket,
        )

    # ==========================================================
    # Typing
    # ==========================================================

    async def typing(
        self,
        conversation_id: UUID,
        user_id: UUID,
    ):
        await events.typing(
            conversation_id,
            user_id,
        )

    # ==========================================================
    # Stop Typing
    # ==========================================================

    async def stop_typing(
        self,
        conversation_id: UUID,
        user_id: UUID,
    ):
        await events.stop_typing(
            conversation_id,
            user_id,
        )

    # ==========================================================
    # Ping
    # ==========================================================

    async def ping(
        self,
        websocket: WebSocket,
    ):
        await events.pong(websocket)


presence_handler = PresenceHandler()