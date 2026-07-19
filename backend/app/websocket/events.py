from enum import Enum


class WebSocketEvent(str, Enum):
    """
    Supported websocket events.
    """

    MESSAGE = "message"

    TYPING = "typing"

    STOP_TYPING = "stop_typing"

    READ = "read"

    PRESENCE = "presence"

    PING = "ping"

    PONG = "pong"