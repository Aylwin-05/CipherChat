from uuid import UUID

from app.models.user import User
from app.services.websocket_service import WebSocketService


class RealtimeService:
    """
    Coordinates all realtime websocket features.

    This service acts as the entry point for every
    websocket event.

    Examples:
        - Message
        - Typing
        - Presence
        - Read Receipts
        - Encryption
    """

    def __init__(
        self,
        websocket_service: WebSocketService,
    ):
        self.websocket_service = websocket_service

    # ==========================================================
    # Message
    # ==========================================================

    async def message(
        self,
        conversation_id: UUID,
        current_user: User,
        content: str,
    ):

        return await self.websocket_service.handle_message(
            conversation_id,
            current_user,
            content,
        )