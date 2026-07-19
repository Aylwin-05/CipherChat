from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


# ==========================================================
# Base Event
# ==========================================================

class WebSocketEvent(BaseModel):
    """
    Base WebSocket event.
    """

    event: str

    model_config = ConfigDict(
        extra="ignore",
    )


# ==========================================================
# Connected Event
# ==========================================================

class ConnectedEvent(WebSocketEvent):
    event: Literal["connected"] = "connected"

    user_id: UUID
    conversation_id: UUID


# ==========================================================
# Chat Message (Incoming)
# ==========================================================

class MessageEvent(WebSocketEvent):
    event: Literal["message"] = "message"

    content: str


# ==========================================================
# Chat Message (Outgoing)
# ==========================================================

class MessageResponse(WebSocketEvent):
    event: Literal["message"] = "message"

    id: UUID
    conversation_id: UUID
    sender_id: UUID
    content: str
    created_at: datetime


# ==========================================================
# Typing
# ==========================================================

class TypingEvent(WebSocketEvent):
    event: Literal["typing"] = "typing"


class StopTypingEvent(WebSocketEvent):
    event: Literal["stop_typing"] = "stop_typing"


# ==========================================================
# Presence
# ==========================================================

class PresenceEvent(WebSocketEvent):
    event: Literal["online", "offline"]

    user_id: UUID


# ==========================================================
# Ping / Pong
# ==========================================================

class PingEvent(WebSocketEvent):
    event: Literal["ping"] = "ping"


class PongEvent(WebSocketEvent):
    event: Literal["pong"] = "pong"


# ==========================================================
# Read Receipt
# ==========================================================

class ReadReceiptEvent(WebSocketEvent):
    event: Literal["read"] = "read"

    message_id: UUID