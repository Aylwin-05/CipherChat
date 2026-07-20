from uuid import UUID

from fastapi import WebSocket

from app.models.message import Message
from app.models.user import User
from app.repositories.conversation_repository import (
    ConversationRepository,
)
from app.repositories.message_repository import (
    MessageRepository,
)
from app.websocket.connection_manager import manager


class WebSocketService:
    """
    Central WebSocket business logic.

    Handles:
    - Authorization
    - Event dispatching
    - Message persistence
    - Typing
    - Delivered receipts
    - Read receipts
    - Ping/Pong
    """

    def __init__(self, db):
        self.db = db

        self.conversation_repository = (
            ConversationRepository(db)
        )

        self.message_repository = (
            MessageRepository(db)
        )

    # ==========================================================
    # Authorization
    # ==========================================================

    async def verify_access(
        self,
        conversation_id: UUID,
        current_user: User,
    ) -> bool:

        participants = (
            await self.conversation_repository.get_participants(
                conversation_id
            )
        )

        return any(
            participant.user_id == current_user.id
            for participant in participants
        )

    # ==========================================================
    # Event Dispatcher
    # ==========================================================

    async def handle_event(
        self,
        websocket: WebSocket,
        conversation_id: UUID,
        current_user: User,
        data: dict,
    ):

        event = data.get("event")

        match event:

            case "message":
                await self.handle_message(
                    conversation_id,
                    current_user,
                    data,
                )

            case "typing":
                await self.handle_typing(
                    conversation_id,
                    current_user,
                )

            case "stop_typing":
                await self.handle_stop_typing(
                    conversation_id,
                    current_user,
                )

            case "delivered":
                await self.handle_delivered(
                    conversation_id,
                    current_user,
                    data,
                )

            case "read":
                await self.handle_read(
                    conversation_id,
                    current_user,
                    data,
                )

            case "ping":
                await websocket.send_json(
                    {
                        "event": "pong",
                    }
                )

            case _:
                raise ValueError(
                    f"Unknown websocket event: {event}"
                )

    # ==========================================================
    # Send Message
    # ==========================================================

    async def handle_message(
        self,
        conversation_id: UUID,
        current_user: User,
        data: dict,
    ):

        content = data.get(
            "content",
            "",
        ).strip()

        if not content:
            raise ValueError(
                "Message cannot be empty."
            )

        message = await self.save_message(
            conversation_id,
            current_user,
            content,
        )

        await manager.broadcast(
            conversation_id,
            {
                "event": "message",
                "id": str(message.id),
                "conversation_id": str(
                    conversation_id
                ),
                "sender_id": str(
                    current_user.id
                ),
                "content": message.content,
                "created_at": message.created_at.isoformat(),
                "delivered_at": None,
                "read_at": None,
            },
        )

    # ==========================================================
    # Delivered Receipt
    # ==========================================================

    async def handle_delivered(
        self,
        conversation_id: UUID,
        current_user: User,
        data: dict,
    ):

        message_id = UUID(
            data["message_id"]
        )

        message = (
            await self.message_repository.get_by_id(
                message_id
            )
        )

        if message is None:
            raise ValueError(
                "Message not found."
            )

        await self.message_repository.mark_delivered(
            message
        )

        await manager.broadcast(
            conversation_id,
            {
                "event": "delivered",
                "message_id": str(message.id),
                "user_id": str(current_user.id),
                "delivered_at": (
                    message.delivered_at.isoformat()
                    if message.delivered_at
                    else None
                ),
            },
        )

    # ==========================================================
    # Read Receipt
    # ==========================================================

    async def handle_read(
        self,
        conversation_id: UUID,
        current_user: User,
        data: dict,
    ):

        message_id = UUID(
            data["message_id"]
        )

        message = (
            await self.message_repository.get_by_id(
                message_id
            )
        )

        if message is None:
            raise ValueError(
                "Message not found."
            )

        await self.message_repository.mark_read(
            message
        )

        await manager.broadcast(
            conversation_id,
            {
                "event": "read",
                "message_id": str(message.id),
                "user_id": str(current_user.id),
                "read_at": (
                    message.read_at.isoformat()
                    if message.read_at
                    else None
                ),
            },
        )

    # ==========================================================
    # Typing
    # ==========================================================

    async def handle_typing(
        self,
        conversation_id: UUID,
        current_user: User,
    ):

        await manager.broadcast(
            conversation_id,
            {
                "event": "typing",
                "user_id": str(
                    current_user.id
                ),
            },
        )

    # ==========================================================
    # Stop Typing
    # ==========================================================

    async def handle_stop_typing(
        self,
        conversation_id: UUID,
        current_user: User,
    ):

        await manager.broadcast(
            conversation_id,
            {
                "event": "stop_typing",
                "user_id": str(
                    current_user.id
                ),
            },
        )

    # ==========================================================
    # Save Message
    # ==========================================================

    async def save_message(
        self,
        conversation_id: UUID,
        current_user: User,
        content: str,
    ) -> Message:

        message = Message(
            conversation_id=conversation_id,
            sender_id=current_user.id,
            content=content,
        )

        return await self.message_repository.create_message(
            message
        )