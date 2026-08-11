import asyncio
import json
import logging
import time
from collections import defaultdict
from uuid import UUID

from fastapi import WebSocket

from app.database.session import AsyncSessionLocal

logger = logging.getLogger("app.websocket.connection_manager")

# A socket that stops draining (suspended/hidden tab) would otherwise
# block send() on flow control for as long as the TCP buffer is full,
# freezing REST endpoints that broadcast (edit/delete/reaction). Cap
# every send and drop the socket if it cannot keep up.
SEND_TIMEOUT_SECONDS = 3.0


async def _send_payload(
    websocket: WebSocket,
    payload: dict,
):
    encoded = json.dumps(
        payload,
        default=str,
    )

    await asyncio.wait_for(
        websocket.send_text(encoded),
        timeout=SEND_TIMEOUT_SECONDS,
    )


class ConnectionManager:
    """
    User-scoped WebSocket connection manager.

    One socket per user (route /ws/me) receives events for ALL of
    that user's conversations, so the sidebar (presence dots, unread
    pills, conversation ordering) updates in real time too.
    """

    def __init__(self):
        # user_id -> list[WebSocket]
        self.user_connections = defaultdict(list)

        # user_id -> set of member user_ids sharing a conversation
        # with that user. Resolved once per connect (see
        # cache_user_members): presence fan-out then never stalls
        # behind a second database connection while the socket's
        # own session still holds an open transaction.
        self.user_members: dict[UUID, set[UUID]] = {}

        # user_id -> time.monotonic() of their most recent connect.
        # Presence snapshots only report peers who were ALREADY
        # online when the snapshot's user connected: peers that
        # connect later announce themselves in their own connect
        # broadcast, so echoing them here would be a duplicate.
        self.user_connected_at: dict[UUID, float] = {}

    # ==========================================================
    # Connect
    # ==========================================================

    async def connect_user(
        self,
        user_id: UUID,
        websocket: WebSocket,
    ):
        if not self.user_connections[user_id]:
            self.user_connected_at[user_id] = (
                time.monotonic()
            )

        self.user_connections[user_id].append(
            websocket
        )

        logger.debug(
            "WS connect: user=%s online=%s",
            user_id,
            list(self.user_connections.keys()),
        )

    # ==========================================================
    # Disconnect
    # ==========================================================

    def disconnect_user(
        self,
        user_id: UUID,
        websocket: WebSocket,
    ):
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
                self.user_connected_at.pop(
                    user_id,
                    None,
                )

        logger.debug(
            "User disconnect: user=%s remaining=%s",
            user_id,
            list(self.user_connections.keys()),
        )

    # ==========================================================
    # Database-backed membership helpers
    # ==========================================================

    async def cache_user_members(
        self,
        user_id: UUID,
        db,
    ):
        # Runs on the CALLER's session (the websocket endpoint's
        # own session) so it never waits on a second connection.
        from sqlalchemy import select

        from app.models.conversation_participant import (
            ConversationParticipant,
        )

        member_ids = set()

        result = await db.execute(
            select(
                ConversationParticipant
            ).where(
                ConversationParticipant.user_id
                == user_id
            )
        )

        for participant in result.scalars().all():
            peers = await db.execute(
                select(
                    ConversationParticipant.user_id
                ).where(
                    ConversationParticipant.conversation_id
                    == participant.conversation_id
                )
            )
            member_ids.update(
                peers.scalars().all()
            )

        self.user_members[user_id] = member_ids

        logger.debug(
            "WS members cached: user=%s members=%d",
            user_id,
            len(member_ids),
        )

    async def _member_ids(
        self,
        conversation_id: UUID,
    ):
        from sqlalchemy import select

        from app.models.conversation_participant import (
            ConversationParticipant,
        )

        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(
                    ConversationParticipant.user_id
                ).where(
                    ConversationParticipant.conversation_id
                    == conversation_id
                )
            )

            return result.scalars().all()

    async def _user_conversation_ids(
        self,
        user_id: UUID,
    ):
        from sqlalchemy import select

        from app.models.conversation_participant import (
            ConversationParticipant,
        )

        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(
                    ConversationParticipant.conversation_id
                ).where(
                    ConversationParticipant.user_id
                    == user_id
                )
            )

            return result.scalars().all()

    async def _peers_for(
        self,
        user_id: UUID,
    ):
        cached = self.user_members.get(user_id)

        if cached is not None:
            return cached

        conversation_ids = (
            await self._user_conversation_ids(user_id)
        )

        peers = set()

        for conversation_id in conversation_ids:
            peers.update(
                await self._member_ids(conversation_id)
            )

        self.user_members[user_id] = peers

        return peers

    # ==========================================================
    # Broadcast to a Conversation
    #
    # Resolves the conversation's members from the database and
    # delivers the event to every ONLINE device of each member,
    # no matter which conversations their sockets were opened for.
    # ==========================================================

    async def broadcast(
        self,
        conversation_id: UUID,
        message: dict,
    ):
        member_ids = await self._member_ids(
            conversation_id
        )

        for member_id in member_ids:
            await self.send_to_user(
                member_id,
                message,
            )

    # ==========================================================
    # Send to One User (all their devices)
    # ==========================================================

    async def send_to_user(
        self,
        user_id: UUID,
        message: dict,
    ):
        if user_id not in self.user_connections:
            return

        if user_id in self.user_connections:
            logger.debug(
                "Sending %s to %d sockets of user %s",
                message.get("event"),
                len(self.user_connections[user_id]),
                user_id,
            )

        dead = []

        for websocket in self.user_connections[user_id]:
            try:
                await _send_payload(
                    websocket,
                    message,
                )

            except Exception as e:
                logger.warning(
                    "Dropping stuck socket: %s",
                    e,
                )
                dead.append(websocket)

        if dead:
            self.user_connections[user_id] = [
                ws
                for ws in self.user_connections[user_id]
                if ws not in dead
            ]

    # ==========================================================
    # Presence
    # ==========================================================

    async def broadcast_presence(
        self,
        user_id: UUID,
        online: bool,
    ):
        peers = await self._peers_for(user_id)

        for peer_id in peers:
            await self.send_to_user(
                peer_id,
                {
                    "event": "presence",
                    "user_id": str(user_id),
                    "online": online,
                },
            )

    async def send_presence_snapshot(
        self,
        user_id: UUID,
    ):
        peers = await self._peers_for(user_id)

        connected_at = self.user_connected_at.get(
            user_id
        )

        if connected_at is None:
            return

        for peer_id in peers:
            if not self.is_online(peer_id):
                continue

            peer_connected_at = (
                self.user_connected_at.get(peer_id)
            )

            # Only peers who were already online when this user
            # connected belong in the snapshot: a peer who connects
            # later announces themselves in their own connect
            # broadcast, so echoing them here would be a duplicate.
            if (
                peer_connected_at is None
                or peer_connected_at > connected_at
            ):
                continue

            await self.send_to_user(
                user_id,
                {
                    "event": "presence",
                    "user_id": str(peer_id),
                    "online": True,
                },
            )

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


manager = ConnectionManager()