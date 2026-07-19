from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.database.database import AsyncSessionLocal
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.message_repository import MessageRepository
from app.services.websocket_service import WebSocketService
from app.websocket.auth import WebSocketAuth
from app.websocket.dispatcher import dispatcher
from app.websocket.events import WebSocketEvent
from app.websocket.manager import manager

router = APIRouter()


@router.websocket("/ws/{conversation_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    conversation_id: UUID,
):
    """
    Main websocket endpoint.

    Responsibilities:
    - Authenticate user
    - Verify conversation access
    - Maintain websocket connection
    - Dispatch websocket events
    """

    # ==========================================================
    # Authenticate
    # ==========================================================

    current_user = await WebSocketAuth.authenticate(
        websocket
    )

    if current_user is None:
        return

    # ==========================================================
    # Database Session
    # ==========================================================

    async with AsyncSessionLocal() as db:

        conversation_repository = ConversationRepository(
            db
        )

        message_repository = MessageRepository(
            db
        )

        websocket_service = WebSocketService(
            conversation_repository,
            message_repository,
        )

        # ======================================================
        # Verify Access
        # ======================================================

        allowed = await websocket_service.verify_conversation_access(
            conversation_id,
            current_user,
        )

        if not allowed:
            await websocket.close(code=1008)
            return

        # ======================================================
        # Connect
        # ======================================================

        await manager.connect(
            conversation_id,
            current_user.id,
            websocket,
        )

        print(
            f"✅ {current_user.email} connected to {conversation_id}"
        )

        try:

            while True:

                payload = await websocket.receive_json()

                event = payload.get("event")

                data = payload.get(
                    "data",
                    {},
                )

                # ==================================================
                # Dispatch Custom Events
                # ==================================================

                handled = await dispatcher.dispatch(
                    event,
                    websocket_service=websocket_service,
                    conversation_id=conversation_id,
                    current_user=current_user,
                    websocket=websocket,
                    data=data,
                )

                if handled:
                    continue

                # ==================================================
                # Built-in Events
                # ==================================================

                if event == WebSocketEvent.PING:

                    await websocket.send_json(
                        {
                            "event": WebSocketEvent.PONG,
                        }
                    )

                else:

                    await websocket.send_json(
                        {
                            "event": "error",
                            "message": f"Unknown event: {event}",
                        }
                    )

        except WebSocketDisconnect:

            manager.disconnect(
                conversation_id,
                current_user.id,
            )

            print(
                f"❌ {current_user.email} disconnected from {conversation_id}"
            )

        except Exception as e:

            print(f"WebSocket Error: {e}")

            manager.disconnect(
                conversation_id,
                current_user.id,
            )

            try:
                await websocket.close()
            except Exception:
                pass