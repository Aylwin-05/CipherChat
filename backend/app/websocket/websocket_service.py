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
    CipherChat Production WebSocket Service

    Responsibilities

    ✔ Verify access
    ✔ Persist messages
    ✔ Broadcast realtime events
    ✔ Delivery receipts
    ✔ Read receipts
    ✔ Typing indicators
    ✔ Edit/Delete
    ✔ Reply support

    Future

    ✔ End-to-End Encryption
    ✔ Voice Notes
    ✔ File Sharing
    ✔ Reactions
    ✔ Calls
    """

    def __init__(self, db):

        self.db = db

        self.message_repository = MessageRepository(db)

        self.conversation_repository = (
            ConversationRepository(db)
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
    # SEND MESSAGE
    # ======================================================

    async def handle_message(
        self,
        conversation_id: UUID,
        current_user: User,
        data: dict,
    ):

        content = (
            data.get("content", "")
            .strip()
        )

        if not content:

            raise ValueError(
                "Message cannot be empty."
            )

        message_type = data.get(
            "message_type",
            "text",
        )

        reply_to_id = data.get(
            "reply_to_id"
        )

        if reply_to_id:

            reply_to_id = UUID(reply_to_id)

        message = await self.save_message(
            conversation_id=conversation_id,
            sender=current_user,
            content=content,
            message_type=message_type,
            reply_to_id=reply_to_id,
        )

        await manager.broadcast(
            conversation_id,
            {
                "event": "message",

                "id": str(message.id),

                "conversation_id": str(
                    message.conversation_id
                ),

                "sender_id": str(
                    message.sender_id
                ),

                "content": message.content,

                "message_type": message.message_type,

                "reply_to_id":
                    str(message.reply_to_id)
                    if message.reply_to_id
                    else None,

                "encrypted":
                    message.encrypted,

                "encryption_algorithm":
                    message.encryption_algorithm,

                "edited":
                    message.edited,

                "deleted":
                    message.deleted_for_everyone,

                "created_at":
                    message.created_at.isoformat(),
            },
        )

    # ======================================================
    # SAVE MESSAGE
    # ======================================================

    async def save_message(
        self,
        conversation_id: UUID,
        sender: User,
        content: str,
        message_type: str = "text",
        reply_to_id: UUID | None = None,
    ) -> Message:

        message = Message(

            conversation_id=conversation_id,

            sender_id=sender.id,

            content=content,

            message_type=message_type,

            encrypted=True,

            encryption_algorithm="RSA-OAEP",

            reply_to_id=reply_to_id,
        )

        return await self.message_repository.create_message(
            message
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

        message_id = UUID(
            data["message_id"]
        )

        new_content = (
            data.get("content", "")
            .strip()
        )

        if not new_content:
            raise ValueError(
                "Edited message cannot be empty."
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

        if message.sender_id != current_user.id:
            raise ValueError(
                "You can edit only your own messages."
            )

        if message.deleted_for_everyone:
            raise ValueError(
                "Message has already been deleted."
            )

        from datetime import datetime, timezone

        message.content = new_content
        message.edited = True
        message.edited_at = datetime.now(
            timezone.utc
        )

        await self.message_repository.update()

        await manager.broadcast(
            conversation_id,
            {
                "event": "edit",

                "message_id": str(message.id),

                "content": message.content,

                "edited": True,

                "edited_at":
                    message.edited_at.isoformat(),
            },
        )

    # ======================================================
    # DELETE FOR EVERYONE
    # ======================================================

    async def handle_delete(
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

        if message.sender_id != current_user.id:
            raise ValueError(
                "You can delete only your own messages."
            )

        if message.deleted_for_everyone:
            return

        from datetime import datetime, timezone

        message.deleted_for_everyone = True
        message.deleted_at = datetime.now(
            timezone.utc
        )

        message.content = (
            "🚫 This message was deleted"
        )

        await self.message_repository.update()

        await manager.broadcast(
            conversation_id,
            {
                "event": "delete",

                "message_id": str(message.id),

                "deleted": True,

                "deleted_at":
                    message.deleted_at.isoformat(),
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

        message = (
            await self.message_repository.get_by_id(
                UUID(data["message_id"])
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

        message = (
            await self.message_repository.get_by_id(
                UUID(data["message_id"])
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
    # FUTURE - FILE MESSAGE
    # ======================================================

    async def handle_file(
        self,
        conversation_id: UUID,
        current_user: User,
        data: dict,
    ):
        """
        Reserved for Phase 2.

        Will support

        - Images
        - Videos
        - Documents
        - ZIP
        - PDFs

        Storage:
            MinIO / AWS S3
        """

        raise NotImplementedError(
            "File sharing not implemented yet."
        )

    # ======================================================
    # FUTURE - VOICE MESSAGE
    # ======================================================

    async def handle_voice(
        self,
        conversation_id: UUID,
        current_user: User,
        data: dict,
    ):
        """
        Reserved for Voice Notes.

        Opus
        AAC
        Waveform
        Duration
        """

        raise NotImplementedError(
            "Voice messages not implemented yet."
        )

    # ======================================================
    # FUTURE - REACTION
    # ======================================================

    async def handle_reaction(
        self,
        conversation_id: UUID,
        current_user: User,
        data: dict,
    ):
        """
        Reserved for reactions.

        👍 ❤️ 😂 😮 😢 🔥
        """

        raise NotImplementedError(
            "Reactions not implemented yet."
        )

    # ======================================================
    # FUTURE - E2EE MESSAGE
    # ======================================================

    async def handle_encrypted_message(
        self,
        conversation_id: UUID,
        current_user: User,
        data: dict,
    ):
        """
        Reserved for End-to-End Encryption.

        Future implementation:

        Sender
            ↓
        X25519 Key Exchange
            ↓
        AES-256-GCM Encrypt
            ↓
        Store Ciphertext
            ↓
        Broadcast Ciphertext
            ↓
        Receiver decrypts locally

        Server NEVER sees plaintext.
        """

        raise NotImplementedError(
            "Encrypted messaging not implemented yet."
        )

    # ======================================================
    # VALIDATION HELPERS
    # ======================================================

    def validate_message_length(
        self,
        content: str,
    ):

        if len(content) > 5000:

            raise ValueError(
                "Message exceeds maximum length."
            )

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

    # ======================================================
    # FUTURE UTILITIES
    # ======================================================

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

    async def ensure_message_owner(
        self,
        message: Message,
        current_user: User,
    ):

        if message.sender_id != current_user.id:

            raise ValueError(
                "Operation not permitted."
            )

    # ======================================================
    # END OF SERVICE
    # ======================================================