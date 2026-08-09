import logging
from collections import defaultdict
from uuid import UUID

from fastapi import WebSocket

logger = logging.getLogger("app.websocket.connection_manager")


class ConnectionManager:
    """
    Production-ready WebSocket connection manager.

    Stores:
    - Active sockets by conversation
    - Active sockets by user
    """

    def __init__(self):
        # conversation_id -> list[(user_id, websocket)]
        self.conversation_connections = defaultdict(list)

        # user_id -> list[WebSocket]
        self.user_connections = defaultdict(list)

    # ==========================================================
    # Connect
    # ==========================================================

    async def connect(
        self,
        conversation_id: UUID,
        user_id: UUID,
        websocket: WebSocket,
    ):
        self.conversation_connections[
            conversation_id
        ].append(
            (
                user_id,
                websocket,
            )
        )

        self.user_connections[user_id].append(
            websocket
        )

        logger.debug(
            "WS connect: user=%s conversation=%s online=%s",
            user_id,
            conversation_id,
            list(self.user_connections.keys()),
        )

    # ==========================================================
    # Disconnect
    # ==========================================================

    def disconnect(
        self,
        conversation_id: UUID,
        user_id: UUID,
        websocket: WebSocket,
    ):
        if (
            conversation_id
            in self.conversation_connections
        ):
            self.conversation_connections[
                conversation_id
            ] = [
                (uid, ws)
                for uid, ws in self.conversation_connections[
                    conversation_id
                ]
                if ws != websocket
            ]

            if (
                not self.conversation_connections[
                    conversation_id
                ]
            ):
                del self.conversation_connections[
                    conversation_id
                ]

        if user_id in self.user_connections:
            self.user_connections[user_id] = [
                ws
                for ws in self.user_connections[
                    user_id
                ]
                if ws != websocket
            ]

            if not self.user_connections[user_id]:
                del self.user_connections[user_id]

        logger.debug(
            "User disconnect: user=%s remaining=%s",
            user_id,
            list(self.user_connections.keys()),
        )

    # ==========================================================
    # Broadcast to Conversation
    # ==========================================================

    async def broadcast(
        self,
        conversation_id: UUID,
        message: dict,
    ):
        if (
            conversation_id
            not in self.conversation_connections
        ):
            return

        dead = []

        if self.conversation_connections.get(conversation_id):
            logger.debug(
                "Broadcasting to %d sockets in conversation %s",
                len(self.conversation_connections[conversation_id]),
                conversation_id,
            )

        for _, websocket in self.conversation_connections[
            conversation_id
        ]:
            try:
                await websocket.send_json(message)

            except Exception:
                dead.append(websocket)

        if dead:
            self.conversation_connections[
                conversation_id
            ] = [
                (uid, ws)
                for uid, ws in self.conversation_connections[
                    conversation_id
                ]
                if ws not in dead
            ]

    # ==========================================================
    # Send to One User
    # ==========================================================

    async def send_to_user(
        self,
        user_id: UUID,
        message: dict,
    ):
        if user_id not in self.user_connections:
            return

        dead = []

        for websocket in self.user_connections[user_id]:
            try:
                await websocket.send_json(message)

            except Exception:
                dead.append(websocket)

        if dead:
            self.user_connections[user_id] = [
                ws
                for ws in self.user_connections[user_id]
                if ws not in dead
            ]

    # ==========================================================
    # Utility Methods
    # ==========================================================

    def is_online(
        self,
        user_id: UUID,
    ) -> bool:

        online = (
            user_id in self.user_connections
            and len(self.user_connections[user_id]) > 0
        )

        return online

    def online_users(self):

        return list(
            self.user_connections.keys()
        )

    def active_conversations(self):
        return list(
            self.conversation_connections.keys()
        )


manager = ConnectionManager()