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

# How long a ringing call_offer stays pending for offline members
# before it is dropped (matches a typical ring duration).
PENDING_CALL_TTL_SECONDS = 45


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

        # user_id -> set of user_ids they blocked (either direction
        # of a block hides presence and blocks message delivery,
        # WhatsApp-style). Loaded once per connect like user_members.
        self.user_blocked: dict[UUID, set[UUID]] = {}
        self.user_blocked_by: dict[UUID, set[UUID]] = {}

        # user_id -> time.monotonic() of their most recent connect.
        # Presence snapshots only report peers who were ALREADY
        # online when the snapshot's user connected: peers that
        # connect later announce themselves in their own connect
        # broadcast, so echoing them here would be a duplicate.
        self.user_connected_at: dict[UUID, float] = {}

        # call_id -> pending call_offer. Kept for PENDING_CALL_TTL so
        # a member whose socket was down (background tab, reconnect
        # gap) still receives the ringing offer when they (re)connect
        # instead of losing the call silently. Removed on call_end.
        self.pending_calls: dict[str, dict] = {}

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

        from app.models.block import Block

        blocked_result = await db.execute(
            select(Block.blocked_id).where(
                Block.blocker_id == user_id
            )
        )

        self.user_blocked[user_id] = set(
            blocked_result.scalars().all()
        )

        blocked_by_result = await db.execute(
            select(Block.blocker_id).where(
                Block.blocked_id == user_id
            )
        )

        self.user_blocked_by[user_id] = set(
            blocked_by_result.scalars().all()
        )

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

    async def _blocked_peers(
        self,
        user_id: UUID,
    ) -> set[UUID]:
        """
        User ids the given user must not interact with: everyone
        they blocked plus everyone who blocked them.
        """

        blocked = self.user_blocked.get(user_id)
        blocked_by = self.user_blocked_by.get(user_id)

        if blocked is None or blocked_by is None:

            from app.models.block import Block

            async with AsyncSessionLocal() as db:

                blocked_result = await db.execute(
                    select(Block.blocked_id).where(
                        Block.blocker_id == user_id
                    )
                )

                blocked_by_result = await db.execute(
                    select(Block.blocker_id).where(
                        Block.blocked_id == user_id
                    )
                )

                blocked = set(
                    blocked_result.scalars().all()
                )

                blocked_by = set(
                    blocked_by_result.scalars().all()
                )

                self.user_blocked[user_id] = blocked
                self.user_blocked_by[user_id] = blocked_by

        return blocked | blocked_by

    # ==========================================================
    # Block cache
    # ==========================================================

    def invalidate_blocks(self, user_id: UUID) -> None:
        """Drop the cached block sets so the next relay re-reads them.

        Called by the block/unblock endpoints: without this, a block
        (or unblock) made while both users' sockets stay connected
        kept silently filtering relays (messages AND calls) until the
        next reconnect.
        """

        self.user_blocked.pop(user_id, None)
        self.user_blocked_by.pop(user_id, None)

    # ==========================================================
    # Pending calls
    # ==========================================================

    async def deliver_pending_calls(self, user_id: UUID) -> None:
        """Deliver ringing call offers the user missed while offline.

        Runs right after a socket (re)connects: every pending offer
        for a conversation the user belongs to is replayed, so an
        incoming call is never lost to a reconnect gap or a closed
        browser tab. Offers expire after PENDING_CALL_TTL_SECONDS
        (or when the caller hangs up).
        """

        self._sweep_pending_calls()

        if not self.pending_calls:
            return

        for call_id, pending in list(self.pending_calls.items()):

            members = await self._member_ids(
                UUID(pending["conversation_id"])
            )

            if user_id in members:

                await self.send_to_user(
                    user_id,
                    pending["payload"],
                )

    def store_pending_call(
        self,
        conversation_id: UUID,
        payload: dict,
    ) -> None:
        """Remember a ringing call_offer for offline members."""

        self._sweep_pending_calls()

        self.pending_calls[payload["call_id"]] = {
            "conversation_id": str(conversation_id),
            "payload": payload,
            "expires_at": (
                time.monotonic()
                + PENDING_CALL_TTL_SECONDS
            ),
        }

    def drop_pending_call(self, call_id: str) -> None:
        """Forget a call that ended, was declined or was answered."""

        self.pending_calls.pop(call_id, None)

    def connected_user_ids(self) -> set[UUID]:
        """Users with at least one live socket (push fallback target)."""

        return set(self.user_connections.keys())

    def _sweep_pending_calls(self) -> None:
        """Drop offers whose ring window already elapsed."""

        if not self.pending_calls:
            return

        now = time.monotonic()

        expired = [
            call_id
            for call_id, pending in self.pending_calls.items()
            if pending["expires_at"] < now
        ]

        for call_id in expired:
            self.pending_calls.pop(call_id, None)

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
        exclude_user_ids: set[UUID] | None = None,
    ):
        member_ids = await self._member_ids(
            conversation_id
        )

        if exclude_user_ids:

            member_ids = [
                member_id
                for member_id in member_ids
                if member_id not in exclude_user_ids
            ]

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

        hidden = await self._blocked_peers(user_id)

        for peer_id in peers:
            if peer_id in hidden:
                continue

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

        hidden = await self._blocked_peers(user_id)

        for peer_id in peers:
            if peer_id in hidden:
                continue

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