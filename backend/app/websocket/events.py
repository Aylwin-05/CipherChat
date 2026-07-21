from uuid import UUID

from fastapi import WebSocket

from app.websocket.connection_manager import manager
from app.websocket.schemas import (
    MessageResponse,
    PongEvent,
)


class WebSocketEvents:
    """
    Handles all outgoing WebSocket events.

    This class does not contain business logic.
    It only formats and sends events.
    """

    # ==========================================================
    # Connected
    # ==========================================================

    async def connected(
        self,
        websocket: WebSocket,
        user_id: UUID,
        conversation_id: UUID,
    ):
        await websocket.send_json(
            {
                "event": "connected",
                "user_id": str(user_id),
                "conversation_id": str(
                    conversation_id
                ),
            }
        )

    # ==========================================================
    # Chat Message
    # ==========================================================

    async def message(
        self,
        conversation_id: UUID,
        message,
    ):
        payload = MessageResponse(
            id=message.id,
            conversation_id=message.conversation_id,
            sender_id=message.sender_id,
            content=message.content,
            created_at=message.created_at,
        )

        await manager.broadcast(
            conversation_id,
            payload.model_dump(mode="json"),
        )

    # ==========================================================
    # Presence
    # ==========================================================

    async def presence(
        self,
        conversation_id: UUID,
        user_id: UUID,
        online: bool,
    ):
        print(
    {
        "event": "presence",
        "user_id": str(user_id),
        "online": online,
    }
)
        await manager.broadcast(
            conversation_id,
            {
                "event": "presence",
                "user_id": str(user_id),
                "online": online,
            },
        )

    # ==========================================================
    # Typing
    # ==========================================================

    async def typing(
        self,
        conversation_id: UUID,
        user_id: UUID,
    ):
        await manager.broadcast(
            conversation_id,
            {
                "event": "typing",
                "user_id": str(user_id),
            },
        )

    # ==========================================================
    # Stop Typing
    # ==========================================================

    async def stop_typing(
        self,
        conversation_id: UUID,
        user_id: UUID,
    ):
        await manager.broadcast(
            conversation_id,
            {
                "event": "stop_typing",
                "user_id": str(user_id),
            },
        )

    # ==========================================================
    # Pong
    # ==========================================================

    async def pong(
        self,
        websocket: WebSocket,
    ):
        payload = PongEvent()

        await websocket.send_json(
            payload.model_dump(mode="json")
        )


events = WebSocketEvents()

