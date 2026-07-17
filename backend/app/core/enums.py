from enum import Enum


class OnlineStatus(str, Enum):
    """
    Represents the user's current presence status.
    """

    ONLINE = "online"
    OFFLINE = "offline"
    AWAY = "away"
    BUSY = "busy"