from collections import defaultdict
from uuid import UUID

from fastapi import WebSocket


class ConnectionManager:
    """
    Production-ready websocket connection manager.

    Structure:

    conversation_id
        │
        ▼
    {
        user_id: websocket
    }
    """

    def __init__(self):

        self.connections: dict[
            UUID,
            dict[
                UUID,
                WebSocket,
            ],
        ] = defaultdict(dict)

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

        self.connections[
            conversation_id
        ][user_id] = websocket

    # ==========================================================
    # Disconnect
    # ==========================================================

    def disconnect(
        self,
        conversation_id: UUID,
        user_id: UUID,
    ):

        if conversation_id not in self.connections:
            return

        self.connections[
            conversation_id
        ].pop(
            user_id,
            None,
        )

        if (
            len(
                self.connections[
                    conversation_id
                ]
            )
            == 0
        ):
            del self.connections[
                conversation_id
            ]

    # ==========================================================
    # Broadcast
    # ==========================================================

    async def broadcast(
        self,
        conversation_id: UUID,
        payload: dict,
    ):

        if (
            conversation_id
            not in self.connections
        ):
            return

        disconnected = []

        for (
            user_id,
            websocket,
        ) in self.connections[
            conversation_id
        ].items():

            try:

                await websocket.send_json(
                    payload
                )

            except Exception:

                disconnected.append(
                    user_id
                )

        for user_id in disconnected:

            self.disconnect(
                conversation_id,
                user_id,
            )

    # ==========================================================
    # Send To One User
    # ==========================================================

    async def send_to_user(
        self,
        conversation_id: UUID,
        user_id: UUID,
        payload: dict,
    ):

        websocket = (
            self.connections
            .get(
                conversation_id,
                {},
            )
            .get(user_id)
        )

        if websocket is None:
            return

        await websocket.send_json(
            payload
        )

    # ==========================================================
    # Online
    # ==========================================================

    def is_online(
        self,
        conversation_id: UUID,
        user_id: UUID,
    ) -> bool:

        return (
            user_id
            in self.connections.get(
                conversation_id,
                {},
            )
        )

    # ==========================================================
    # Connected Users
    # ==========================================================

    def connected_users(
        self,
        conversation_id: UUID,
    ):

        return list(
            self.connections.get(
                conversation_id,
                {},
            ).keys()
        )


manager = ConnectionManager()