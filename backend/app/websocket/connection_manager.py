from collections import defaultdict
from uuid import UUID

from fastapi import WebSocket


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
        await websocket.accept()

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

        print("\n========== CONNECT ==========")
        print(f"User: {user_id}")
        print(f"Conversation: {conversation_id}")
        print("Current Online Users:")
        print(list(self.user_connections.keys()))
        print("=============================\n")

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

        print("\n======== DISCONNECT =========")
        print(f"User: {user_id}")
        print("Remaining Online Users:")
        print(list(self.user_connections.keys()))
        print("=============================\n")

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

        print(
            f"Broadcasting to {len(self.conversation_connections[conversation_id])} sockets"
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

        print("\n========== ONLINE CHECK ==========")
        print(f"Checking User: {user_id}")
        print("Current Online Users:")
        print(list(self.user_connections.keys()))

        online = (
            user_id in self.user_connections
            and len(self.user_connections[user_id]) > 0
        )

        print(f"Result: {online}")
        print("==================================\n")

        return online

    def online_users(self):
        print("\nONLINE USERS:")
        print(list(self.user_connections.keys()))
        print()

        return list(
            self.user_connections.keys()
        )

    def active_conversations(self):
        return list(
            self.conversation_connections.keys()
        )


manager = ConnectionManager()