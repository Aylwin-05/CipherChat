from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.api import api_router
from app.core.config import settings
from app.database.session import get_db

app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    debug=settings.DEBUG,
)

# ==========================================================
# Register API Routes
# ==========================================================

app.include_router(
    api_router,
    prefix="/api/v1",
)

# ==========================================================
# Root Endpoint
# ==========================================================

@app.get("/", tags=["System"])
async def root():
    return {
        "application": settings.APP_NAME,
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs",
    }

# ==========================================================
# Health Check
# ==========================================================

@app.get("/health", tags=["System"])
async def health(
    db: AsyncSession = Depends(get_db),
):
    """
    Health check endpoint.
    """

    try:
        await db.execute(text("SELECT 1"))
        database_status = "connected"

    except Exception as e:
        print(f"Health Check Error: {e}")
        database_status = "disconnected"

    return {
        "status": "healthy",
        "database": database_status,
        "environment": settings.APP_ENV,
    }