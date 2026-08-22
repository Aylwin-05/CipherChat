from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.database.session import get_db
from app.dependencies.auth import get_current_user
from app.dependencies.rate_limit import rate_limit
from app.models.user import User

router = APIRouter(
    prefix="/call",
    tags=["Calls"],
)


# ==========================================================
# WebRTC ICE configuration
#
# Returns the ICE servers the client should use for voice and
# video calls. Media itself is end-to-end encrypted on the
# client (insertable streams); TURN servers only relay opaque
# encrypted RTP packets, so they never see call content.
#
# In production you would mint short-lived TURN credentials
# per user here; this static config is safe to extend.
# ==========================================================

@router.get(
    "/config",
    dependencies=[
        rate_limit("call.config", 30, 60),
    ],
)
async def call_config(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):

    ice_servers = [
        {
            "urls": "stun:stun.l.google.com:19302",
        },
    ]

    turn_urls = [
        url.strip()
        for url in settings.TURN_URLS.split(",")
        if url.strip()
    ]

    if turn_urls:

        ice_servers.append(
            {
                "urls": turn_urls,
                "username": settings.TURN_USERNAME,
                "credential": settings.TURN_PASSWORD,
            }
        )

    return {
        "ice_servers": ice_servers,
        "e2ee_supported": True,
    }