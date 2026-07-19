from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import AsyncSessionLocal
from app.dependencies.websocket_auth import websocket_auth
from app.models.user import User
from app.repositories.auth_repository import AuthRepository
from app.websocket.connection_manager import manager
from app.websocket.websocket_service import WebSocketService

router = APIRouter()


@router.websocket("/ws/{conversation_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    conversation_id: UUID,
):
    """
    Production WebSocket endpoint.

    Flow:
    JWT Authentication
        ↓
    Load User
        ↓
    Save Message
        ↓
    Broadcast Message
    """

    # ==========================================================
    # Authenticate
    # ==========================================================

    payload = await websocket_auth.authenticate(
        websocket
    )

    if payload is None:
        return

    user_id = UUID(payload["sub"])

    # ==========================================================
    # Database Session
    # ==========================================================

    async with AsyncSessionLocal() as db:

        repository = AuthRepository(db)

        current_user: User | None = (
            await repository.get_user_by_id(
                user_id
            )
        )

        if current_user is None:
            await websocket.close(code=1008)
            return

        websocket_service = WebSocketService(db)

        # ======================================================
        # Connect
        # ======================================================

        await manager.connect(
            conversation_id,
            current_user.id,
            websocket,
        )

        try:

            await websocket.send_json(
                {
                    "event": "connected",
                    "user_id": str(current_user.id),
                    "conversation_id": str(
                        conversation_id
                    ),
                }
            )

            while True:

                data = await websocket.receive_json()

                event = data.get("event")

                # ==========================================
                # Message
                # ==========================================

                if event == "message":

                    content = (
                        data.get("content", "")
                        .strip()
                    )

                    if not content:
                        continue

                    saved_message = (
                        await websocket_service.save_message(
                            conversation_id,
                            current_user,
                            content,
                        )
                    )

                    await manager.broadcast(
                        conversation_id,
                        {
                            "event": "message",
                            "id": str(saved_message.id),
                            "conversation_id": str(
                                conversation_id
                            ),
                            "sender_id": str(
                                current_user.id
                            ),
                            "content": saved_message.content,
                            "created_at": (
                                saved_message.created_at.isoformat()
                            ),
                        },
                    )

                # ==========================================
                # Typing
                # ==========================================

                elif event == "typing":

                    await manager.broadcast(
                        conversation_id,
                        {
                            "event": "typing",
                            "user_id": str(
                                current_user.id
                            ),
                        },
                    )

                # ==========================================
                # Stop Typing
                # ==========================================

                elif event == "stop_typing":

                    await manager.broadcast(
                        conversation_id,
                        {
                            "event": "stop_typing",
                            "user_id": str(
                                current_user.id
                            ),
                        },
                    )

                # ==========================================
                # Ping
                # ==========================================

                elif event == "ping":

                    await websocket.send_json(
                        {
                            "event": "pong",
                        }
                    )

        except WebSocketDisconnect:

            manager.disconnect(
                conversation_id,
                current_user.id,
                websocket,
            )

            print(
                f"WebSocket disconnected: {current_user.email}"
            )

        except Exception as e:

            print(
                f"WebSocket Error: {e}"
            )

            manager.disconnect(
                conversation_id,
                current_user.id,
                websocket,
            )