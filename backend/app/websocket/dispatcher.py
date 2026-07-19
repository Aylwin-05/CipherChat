from app.websocket.events import WebSocketEvent
from app.websocket.handlers.message_handler import (
    message_handler,
)


class EventDispatcher:
    """
    Routes websocket events to their handlers.
    """

    def __init__(self):
        self._handlers = {}

    # ==========================================================
    # Register
    # ==========================================================

    def register(
        self,
        event: WebSocketEvent,
        handler,
    ):
        self._handlers[event] = handler

    # ==========================================================
    # Dispatch
    # ==========================================================

    async def dispatch(
        self,
        event: str,
        **kwargs,
    ):

        handler = self._handlers.get(event)

        if handler is None:
            return False

        await handler(**kwargs)

        return True


dispatcher = EventDispatcher()

# ==========================================================
# Register Built-in Events
# ==========================================================

dispatcher.register(
    WebSocketEvent.MESSAGE,
    message_handler,
)