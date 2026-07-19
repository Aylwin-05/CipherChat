from fastapi import WebSocket

from app.services.jwt_service import JWTService


class WebSocketAuth:
    """
    Handles authentication for WebSocket connections.
    """

    def __init__(self):
        self.jwt_service = JWTService()

    async def authenticate(
        self,
        websocket: WebSocket,
    ):
        """
        Authenticate a websocket using the JWT access token
        provided as a query parameter.

        Example:
        ws://localhost:8000/ws/<conversation_id>?token=<JWT>
        """

        token = websocket.query_params.get("token")

        if not token:
            await websocket.close(code=1008)
            return None

        payload = self.jwt_service.verify_access_token(
            token
        )

        if payload is None:
            await websocket.close(code=1008)
            return None

        return payload


websocket_auth = WebSocketAuth()