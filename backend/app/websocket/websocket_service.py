import logging

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
        current_user: User,
        data: dict,
    ):

        event = data.get("event")

        if event == "ping":

            await self.handle_ping(websocket)

            return

        # The socket is user-scoped (/ws/me), so every real event
        # must declare which conversation it targets AND the sender
        # must be a participant of it.
        conversation_id = UUID(
            data.get("conversation_id", "")
        )

        if not await self.verify_access(
            conversation_id,
            current_user,
        ):
            raise ValueError(
                "Access denied."
            )

        handlers = {

            "message": self.handle_message,

            "typing": self.handle_typing,

            "stop_typing": self.handle_stop_typing,

            "delivered": self.handle_delivered,

            "read": self.handle_read,

            "edit": self.handle_edit,

            "delete": self.handle_delete,

            # Voice/video call signaling (WebRTC). The server only
            # relays SDP/ICE between conversation members - media
            # flows peer-to-peer and is encrypted by DTLS-SRTP, so
            # the backend never sees call content.
            "call_offer": self.handle_call,

            "call_answer": self.handle_call,

            "call_ice": self.handle_call,

            "call_end": self.handle_call,

            "ping": self.handle_ping,

        }

        handler = handlers.get(event)

        if handler is None:

            raise ValueError(
                f"Unknown websocket event '{event}'"
            )

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

                "expires_at":
                    data.get(
                        "expires_at"
                    ),

                "created_at":
                    data["created_at"],

                "updated_at":
                    data.get(
                        "updated_at",
                        data["created_at"],
                    ),
                "attachments":
                    data.get(
                        "attachments",
                        [],
                    ),
                "recipient_keys":
                    data.get(
                        "recipient_keys",
                        [],
                    ),
                "envelopes":
                    data.get(
                        "envelopes",
                        [],
                    ),
                "sync_envelope":
                    data.get(
                        "sync_envelope"
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

        # The edited content arrives already encrypted
        # (Signal ratchet): the server only swaps the payload
        # fields — the edited plaintext never touches it.
        if data.get("ciphertext"):

            message.ciphertext = data["ciphertext"]
            message.encrypted_key_sender = data.get(
                "encrypted_key_sender",
                message.encrypted_key_sender,
            )
            message.encrypted_key_receiver = data.get(
                "encrypted_key_receiver",
                message.encrypted_key_receiver,
            )
            message.nonce = data.get(
                "nonce",
                message.nonce,
            )

            # Group edits carry fresh per-recipient wrapped keys.
            if data.get("recipient_keys"):

                await self.message_repository.replace_recipient_keys(
                    message.id,
                    [
                        (
                            UUID(key["user_id"]),
                            key["encrypted_key"],
                        )
                        for key in data["recipient_keys"]
                    ],
                )

            # Multi-device edits carry fresh per-device envelopes.
            if data.get("envelopes"):

                message.envelopes = [
                    {
                        "device_id": env["device_id"],
                        "data": env["data"],
                    }
                    for env in data["envelopes"]
                ]

            # Edited content is a fresh plaintext: replace the
            # account-key copy so other browsers don't keep the
            # stale text.
            if data.get("sync_envelope"):

                message.sync_envelope = data["sync_envelope"]

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

                "sender_id": str(message.sender_id),

                "edited": True,

                "ciphertext": data.get(
                    "ciphertext",
                    message.ciphertext,
                ),

                "encrypted_key_sender": message.encrypted_key_sender,

                "encrypted_key_receiver": message.encrypted_key_receiver,

                "nonce": message.nonce,

                "recipient_keys": [
                    {
                        "user_id": str(key.user_id),
                        "encrypted_key": key.encrypted_key,
                    }
                    for key in message.recipient_keys
                ]
                if "recipient_keys" in message.__dict__
                else [],

                "envelopes": message.envelopes or [],

                "sync_envelope": message.sync_envelope,

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

        from datetime import datetime, timezone

        # The REST 'delete for everyone' endpoint normally runs
        # first and already sets the flag; this WS event is the
        # real-time notification. Skip the write when it is
        # already deleted, but ALWAYS broadcast so the other
        # participant's UI updates without a reload.
        if not message.deleted_for_everyone:

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
    # VOICE / VIDEO CALL SIGNALING (WebRTC relay)
    #
    # The server is a dumb relay: it validates the conversation
    # membership (already done by the dispatcher), stamps the
    # sender id on the event and broadcasts it to every member.
    # Media itself is P2P (DTLS-SRTP encrypted) and never
    # touches the server.
    # ======================================================

    async def handle_call(
        self,
        conversation_id: UUID,
        current_user: User,
        data: dict,
    ):

        event = data.get("event")

        if not data.get("call_id"):

            raise ValueError(
                "Missing field 'call_id'."
            )

        if event == "call_offer" and not data.get("call_type"):

            raise ValueError(
                "Missing field 'call_type'."
            )

        payload = {

            "event": event,

            "conversation_id": str(conversation_id),

            "call_id": data["call_id"],

            "from": str(current_user.id),

        }

        # Optional addressing: "to" lets callers target one peer
        # (ICE candidates, answers); when absent the event goes
        # to every member.
        if data.get("to"):

            payload["to"] = str(data["to"])

        if data.get("call_type"):

            payload["call_type"] = data["call_type"]

        if data.get("sdp"):

            payload["sdp"] = data["sdp"]

        if data.get("candidate"):

            payload["candidate"] = data["candidate"]

        await manager.broadcast(
            conversation_id,
            payload,
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
                "conversation_id": str(conversation_id),
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
                "conversation_id": str(conversation_id),
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