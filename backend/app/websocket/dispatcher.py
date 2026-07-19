from app.websocket.events import WebSocketEvent
from app.websocket.handlers.delivered_handler import (
    delivered_handler,
)
from app.websocket.handlers.message_handler import (
    message_handler,
)
from app.websocket.handlers.read_handler import (
    read_handler,
)
from app.websocket.handlers.stop_typing_handler import (
    stop_typing_handler,
)
from app.websocket.handlers.typing_handler import (
    typing_handler,
)


class EventDispatcher:
    """
    Routes websocket events to their respective handlers.
    """

    def __init__(self):
        self._handlers = {}

    # ==========================================================
    # Register Event
    # ==========================================================

    def register(
        self,
        event: WebSocketEvent,
        handler,
    ):
        self._handlers[event] = handler

    # ==========================================================
    # Dispatch Event
    # ==========================================================

    async def dispatch(
        self,
        event: str,
        **kwargs,
    ) -> bool:

        handler = self._handlers.get(event)

        if handler is None:
            return False

        await handler(**kwargs)

        return True


dispatcher = EventDispatcher()

# ==========================================================
# Register Events
# ==========================================================

dispatcher.register(
    WebSocketEvent.MESSAGE,
    message_handler,
)

dispatcher.register(
    WebSocketEvent.TYPING,
    typing_handler,
)

dispatcher.register(
    WebSocketEvent.STOP_TYPING,
    stop_typing_handler,
)

dispatcher.register(
    WebSocketEvent.DELIVERED,
    delivered_handler,
)

dispatcher.register(
    WebSocketEvent.READ,
    read_handler,
)