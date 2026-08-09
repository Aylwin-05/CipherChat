from fastapi import APIRouter

from app.api.v1.auth import router as auth_router
from app.api.v1.conversations import (
    router as conversations_router,
)
from app.api.v1.friends import router as friends_router
from app.api.v1.keys import router as keys_router
from app.api.v1.messages import router as messages_router
from app.api.v1.attachments import (
    router as attachments_router,
)
from app.api.v1.users import router as users_router
<<<<<<< HEAD
from app.api.v1.devices import router as devices_router
=======
from app.api.v1 import user_keys
>>>>>>> b1fe404574da5b5ac3ebc7bc51357101824c53c6

api_router = APIRouter()

# ==========================================================
# Authentication
# ==========================================================

api_router.include_router(auth_router)

# ==========================================================
# Users
# ==========================================================

api_router.include_router(users_router)

# ==========================================================
# Devices
# ==========================================================

api_router.include_router(devices_router)

# ==========================================================
# Friends
# ==========================================================

api_router.include_router(friends_router)

# ==========================================================
# Conversations
# ==========================================================

api_router.include_router(conversations_router)

# ==========================================================
# Messages
# ==========================================================

api_router.include_router(messages_router)

# ==========================================================
# Attachments
# ==========================================================

api_router.include_router(attachments_router)

# ==========================================================
# Encryption Keys
# ==========================================================

api_router.include_router(keys_router)

# ==========================================================
# User Keys
# ==========================================================

api_router.include_router(user_keys.router)