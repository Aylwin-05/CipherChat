from uuid import UUID

from fastapi import WebSocket

from app.database.database import AsyncSessionLocal
from app.repositories.auth_repository import AuthRepository
from app.services.jwt_service import JWTService


class WebSocketAuth:
    """
    Handles authentication for WebSocket connections.
    """

    @staticmethod
    async def authenticate(
        websocket: WebSocket,
    ):
        """
        Authenticate websocket using JWT token supplied as:

        ws://host/ws/{conversation_id}?token=JWT
        """

        token = websocket.query_params.get("token")

        if not token:
            await websocket.close(code=1008)
            return None

        jwt_service = JWTService()

        payload = jwt_service.verify_access_token(token)

        if payload is None:
            await websocket.close(code=1008)
            return None

        user_id = payload.get("sub")

        if user_id is None:
            await websocket.close(code=1008)
            return None

        async with AsyncSessionLocal() as db:

            repository = AuthRepository(db)

            user = await repository.get_user_by_id(
                UUID(user_id)
            )

            if user is None:
                await websocket.close(code=1008)
                return None

            return user