from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.database.database import AsyncSessionLocal
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.message_repository import MessageRepository
from app.services.websocket_service import WebSocketService
from app.websocket.auth import WebSocketAuth
from app.websocket.manager import manager

router = APIRouter()


@router.websocket("/ws/{conversation_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    conversation_id: UUID,
):
    """
    Production-ready websocket endpoint.
    """

    # ==========================================================
    # Authenticate User
    # ==========================================================

    current_user = await WebSocketAuth.authenticate(
        websocket
    )

    if current_user is None:
        return

    # ==========================================================
    # Create Services
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
        # Verify Conversation Access
        # ======================================================

        allowed = (
            await websocket_service.verify_conversation_access(
                conversation_id,
                current_user,
            )
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
            f"✅ {current_user.email} connected"
        )

        try:

            while True:

                data = await websocket.receive_json()

                content = data.get(
                    "content",
                    "",
                ).strip()

                if not content:
                    continue

                await websocket_service.handle_message(
                    conversation_id,
                    current_user,
                    content,
                )

        except WebSocketDisconnect:

            manager.disconnect(
                conversation_id,
                current_user.id,
            )

            print(
                f"❌ {current_user.email} disconnected"
            )