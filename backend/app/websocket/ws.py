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


@router.websocket("/ws/{conversation_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    conversation_id: UUID,
):
    """
    Production WebSocket Endpoint.

    Responsibilities:
    - Authenticate user
    - Load user
    - Verify conversation access
    - Connect socket
    - Broadcast presence
    - Delegate events
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
        # Verify Conversation Access
        # ======================================================

        allowed = await websocket_service.verify_access(
            conversation_id,
            current_user,
        )

        if not allowed:
            await websocket.close(code=1008)
            return

        # ======================================================
        # Accept Handshake (echo validated subprotocol)
        # ======================================================

        await websocket.accept(subprotocol=subprotocol)

        # ======================================================
        # Connect
        # ======================================================

        await manager.connect(
            conversation_id,
            current_user.id,
            websocket,
        )

        # Notify current client
        await websocket.send_json(
            {
                "event": "connected",
                "conversation_id": str(conversation_id),
                "user_id": str(current_user.id),
            }
        )

        # Notify everyone in this conversation
        await manager.broadcast(
            conversation_id,
            {
                "event": "presence",
                "user_id": str(current_user.id),
                "online": True,
            },
        )

        logger.info(
            "WS connected: user=%s conversation=%s",
            current_user.email,
            conversation_id,
        )

        # ======================================================
        # Main Loop
        # ======================================================

        try:

            while True:

                data = await websocket.receive_json()

                await websocket_service.handle_event(
                    websocket=websocket,
                    conversation_id=conversation_id,
                    current_user=current_user,
                    data=data,
                )

        except WebSocketDisconnect:

            logger.info(
                "WS disconnected: user=%s conversation=%s",
                current_user.email,
                conversation_id,
            )

        except ValueError as e:

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

                await websocket.send_json(
                    {
                        "event": "error",
                        "message": "Internal server error.",
                    }
                )

            except Exception:
                pass

        finally:

            manager.disconnect(
                conversation_id,
                current_user.id,
                websocket,
            )

            # Notify everyone user went offline
            await manager.broadcast(
                conversation_id,
                {
                    "event": "presence",
                    "user_id": str(current_user.id),
                    "online": False,
                },
            )