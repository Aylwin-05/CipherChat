from uuid import UUID

from fastapi import WebSocket

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
    CipherChat WebSocket Service

    IMPORTANT
    ---------
    WebSocket NEVER stores messages.

    Messages are stored by:

        POST /messages/send

    WebSocket only broadcasts realtime events.

    Responsibilities
    ----------------
    ✓ Verify conversation access
    ✓ Broadcast new encrypted messages
    ✓ Typing indicators
    ✓ Stop typing
    ✓ Read receipts
    ✓ Delivery receipts
    ✓ Edit notifications
    ✓ Delete notifications
    ✓ Ping / Pong
    """

    def __init__(self, db):

        self.db = db

        self.conversation_repository = (
            ConversationRepository(db)
        )

        self.message_repository = (
            MessageRepository(db)
        )

    # ======================================================
    # Authorization
    # ======================================================

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

    # ======================================================
    # Event Dispatcher
    # ======================================================

    async def handle_event(
        self,
        websocket: WebSocket,
        conversation_id: UUID,
        current_user: User,
        data: dict,
    ):

        event = data.get("event")

        handlers = {

            "message": self.handle_message,

            "typing": self.handle_typing,

            "stop_typing": self.handle_stop_typing,

            "delivered": self.handle_delivered,

            "read": self.handle_read,

            "edit": self.handle_edit,

            "delete": self.handle_delete,

            "ping": self.handle_ping,

        }

        handler = handlers.get(event)

        if handler is None:

            raise ValueError(
                f"Unknown websocket event '{event}'"
            )

        if event == "ping":

            await handler(websocket)

            return

        await handler(
            conversation_id,
            current_user,
            data,
        )
            # ======================================================
    # MESSAGE
    #
    # IMPORTANT
    #
    # Message has ALREADY been saved by:
    #
    # POST /messages/send
    #
    # WebSocket only broadcasts it.
    # ======================================================

    async def handle_message(
        self,
        conversation_id: UUID,
        current_user: User,
        data: dict,
    ):

        required = [

            "id",

            "conversation_id",

            "sender_id",

            "ciphertext",

            "encrypted_key_sender",

            "encrypted_key_receiver",

            "nonce",

            "created_at",

        ]

        for field in required:

            if field not in data:

                raise ValueError(
                    f"Missing field '{field}'."
                )

        await manager.broadcast(
            conversation_id,
            {

                "event": "message",

                "id": data["id"],

                "conversation_id":
                    data["conversation_id"],

                "sender_id":
                    data["sender_id"],

                "ciphertext":
                    data["ciphertext"],

                "encrypted_key_sender":
                    data["encrypted_key_sender"],

                "encrypted_key_receiver":
                    data["encrypted_key_receiver"],

                "nonce":
                    data["nonce"],

                "crypto_version":
                    data.get(
                        "crypto_version",
                        1,
                    ),

                "message_type":
                    data.get(
                        "message_type",
                        "text",
                    ),

                "reply_to_id":
                    data.get(
                        "reply_to_id"
                    ),

                "edited":
                    data.get(
                        "edited",
                        False,
                    ),

                "deleted_for_everyone":
                    data.get(
                        "deleted_for_everyone",
                        False,
                    ),

                "is_read":
                    data.get(
                        "is_read",
                        False,
                    ),

                "created_at":
                    data["created_at"],

                "updated_at":
                    data.get(
                        "updated_at",
                        data["created_at"],
                    ),
            },
        )
            # ======================================================
    # EDIT MESSAGE
    # ======================================================

    async def handle_edit(
        self,
        conversation_id: UUID,
        current_user: User,
        data: dict,
    ):

        message_id = UUID(data["message_id"])

        message = await self.message_repository.get_by_id(
            message_id
        )

        if message is None:
            raise ValueError("Message not found.")

        if message.sender_id != current_user.id:
            raise ValueError(
                "You can edit only your own messages."
            )

        if message.deleted_for_everyone:
            raise ValueError(
                "Message has already been deleted."
            )

        from datetime import datetime, timezone

        message.edited = True
        message.updated_at = datetime.now(
            timezone.utc
        )

        await self.message_repository.update()

        await manager.broadcast(
            conversation_id,
            {
                "event": "edit",

                "message_id": str(message.id),

                "edited": True,

                "updated_at":
                    message.updated_at.isoformat(),
            },
        )

    # ======================================================
    # DELETE MESSAGE
    # ======================================================

    async def handle_delete(
        self,
        conversation_id: UUID,
        current_user: User,
        data: dict,
    ):

        message_id = UUID(data["message_id"])

        message = await self.message_repository.get_by_id(
            message_id
        )

        if message is None:
            raise ValueError("Message not found.")

        if message.sender_id != current_user.id:
            raise ValueError(
                "You can delete only your own messages."
            )

        if message.deleted_for_everyone:
            return

        from datetime import datetime, timezone

        message.deleted_for_everyone = True
        message.updated_at = datetime.now(
            timezone.utc
        )

        await self.message_repository.update()

        await manager.broadcast(
            conversation_id,
            {
                "event": "delete",

                "message_id": str(message.id),

                "deleted_for_everyone": True,

                "updated_at":
                    message.updated_at.isoformat(),
            },
        )

    # ======================================================
    # DELIVERED RECEIPT
    # ======================================================

    async def handle_delivered(
        self,
        conversation_id: UUID,
        current_user: User,
        data: dict,
    ):

        message = await self.message_repository.get_by_id(
            UUID(data["message_id"])
        )

        if message is None:
            raise ValueError("Message not found.")

        await self.message_repository.mark_delivered(
            message
        )

        await manager.broadcast(
            conversation_id,
            {
                "event": "delivered",

                "message_id": str(message.id),

                "user_id": str(current_user.id),

                "delivered_at":
                    message.delivered_at.isoformat()
                    if message.delivered_at
                    else None,
            },
        )

    # ======================================================
    # READ RECEIPT
    # ======================================================

    async def handle_read(
        self,
        conversation_id: UUID,
        current_user: User,
        data: dict,
    ):

        message = await self.message_repository.get_by_id(
            UUID(data["message_id"])
        )

        if message is None:
            raise ValueError("Message not found.")

        await self.message_repository.mark_read(
            message
        )

        await manager.broadcast(
            conversation_id,
            {
                "event": "read",

                "message_id": str(message.id),

                "user_id": str(current_user.id),

                "read_at":
                    message.read_at.isoformat()
                    if message.read_at
                    else None,
            },
        )
    # ======================================================
    # TYPING
    # ======================================================

    async def handle_typing(
        self,
        conversation_id: UUID,
        current_user: User,
        data: dict,
    ):

        await manager.broadcast(
            conversation_id,
            {
                "event": "typing",
                "user_id": str(current_user.id),
            },
        )

    # ======================================================
    # STOP TYPING
    # ======================================================

    async def handle_stop_typing(
        self,
        conversation_id: UUID,
        current_user: User,
        data: dict,
    ):

        await manager.broadcast(
            conversation_id,
            {
                "event": "stop_typing",
                "user_id": str(current_user.id),
            },
        )

    # ======================================================
    # PING / PONG
    # ======================================================

    async def handle_ping(
        self,
        websocket: WebSocket,
    ):

        await websocket.send_json(
            {
                "event": "pong",
            }
        )

    # ======================================================
    # VALIDATION HELPERS
    # ======================================================

    def validate_message_type(
        self,
        message_type: str,
    ):

        allowed = {
            "text",
            "image",
            "video",
            "audio",
            "document",
            "system",
        }

        if message_type not in allowed:

            raise ValueError(
                f"Unsupported message type '{message_type}'."
            )

    async def ensure_participant(
        self,
        conversation_id: UUID,
        current_user: User,
    ):

        allowed = await self.verify_access(
            conversation_id,
            current_user,
        )

        if not allowed:

            raise ValueError(
                "Access denied."
            )

    # ======================================================
    # END
    # ======================================================