from fastapi import APIRouter

from app.api.v1.auth import router as auth_router
from app.api.v1.conversations import (
    router as conversations_router,
)
from app.api.v1.friends import router as friends_router
from app.api.v1.messages import router as messages_router
from app.api.v1.users import router as users_router

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