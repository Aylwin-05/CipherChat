import asyncio
import logging
from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.database.session import AsyncSessionLocal
from app.dependencies.websocket_auth import websocket_auth
from app.models.user import User
from app.repositories.auth_repository import AuthRepository
from app.websocket.connection_manager import manager
from app.websocket.websocket_service import WebSocketService

logger = logging.getLogger("app.websocket.ws")

router = APIRouter()


@router.websocket("/ws/me")
async def websocket_endpoint(
    websocket: WebSocket,
):
    """
    User-scoped WebSocket Endpoint.

    One socket per user receives events for ALL of the user's
    conversations (messages, typing, receipts, edits, deletes,
    reactions, attachments, presence), so every part of the UI -
    including the sidebar - updates in real time.
    """

    # ==========================================================
    # Authenticate
    # ==========================================================

    payload, subprotocol = (
        await websocket_auth.authenticate(
            websocket
        )
    )

    if payload is None:
        return

    user_id = UUID(payload["sub"])

    # ==========================================================
    # Database Session
    # ==========================================================

    async with AsyncSessionLocal() as db:

        auth_repository = AuthRepository(db)

        current_user: User | None = (
            await auth_repository.get_user_by_id(
                user_id
            )
        )

        if current_user is None:
            await websocket.close(code=1008)
            return

        websocket_service = WebSocketService(db)

        # ======================================================
        # Accept Handshake (echo validated subprotocol)
        # ======================================================

        await websocket.accept(subprotocol=subprotocol)

        # ======================================================
        # Connect
        # ======================================================

        await manager.connect_user(
            current_user.id,
            websocket,
        )

        # Resolve this user's conversation peers NOW, on this
        # session (no open transaction yet). Everything below -
        # including the disconnect broadcast - then uses the
        # cached membership instead of opening a second database
        # connection that could stall behind this long-lived
        # session's open transaction.
        await manager.cache_user_members(
            current_user.id,
            db,
        )

        # Notify current client
        await websocket.send_json(
            {
                "event": "connected",
                "user_id": str(current_user.id),
            }
        )

        # Notify everyone sharing a conversation with this user
        await manager.broadcast_presence(
            current_user.id,
            True,
        )

        # Tell this client who of their peers is already online
        await manager.send_presence_snapshot(
            current_user.id,
        )

        logger.info(
            "WS connected: user=%s",
            current_user.email,
        )

        # ======================================================
        # Main Loop
        # ======================================================

        try:

            while True:

                data = await websocket.receive_json()

                await websocket_service.handle_event(
                    websocket=websocket,
                    current_user=current_user,
                    data=data,
                )

                # The websocket session is otherwise held open for
                # the whole connection lifetime: any handler write
                # (read/delivered receipts, edit, delete) would stay
                # in an open transaction and keep its PostgreSQL row
                # locks until the socket closes - blocking REST
                # updates on the same message (e.g. edit) forever.
                # Commit after every event to release them promptly.
                await db.commit()

        except WebSocketDisconnect:

            logger.info(
                "WS disconnected: user=%s",
                current_user.email,
            )

        except ValueError as e:

            try:
                await db.rollback()
            except Exception:
                pass

            await websocket.send_json(
                {
                    "event": "error",
                    "message": str(e),
                }
            )

        except Exception as e:

            logger.exception(
                "WebSocket error for user=%s: %s",
                current_user.email,
                e,
            )

            try:
                await db.rollback()
            except Exception:
                pass

            try:

                await websocket.send_json(
                    {
                        "event": "error",
                        "message": "Internal server error.",
                    }
                )

            except Exception:
                pass

        finally:

            manager.disconnect_user(
                current_user.id,
                websocket,
            )

            # The TestClient cancels the websocket task immediately
            # after the client sends its close frame, right as this
            # finally block runs: an unguarded await would be
            # cancelled before the offline event reached a single
            # peer. Shield the broadcast - it is in-memory now
            # (cached membership), so it completes either way - and
            # swallow the teardown CancelledError.
            try:

                await asyncio.shield(
                    manager.broadcast_presence(
                        current_user.id,
                        False,
                    )
                )

            except asyncio.CancelledError:

                pass