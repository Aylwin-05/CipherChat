from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.database.session import get_db

app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    debug=settings.DEBUG,
)


@app.get("/")
async def root():
    return {
        "application": settings.APP_NAME,
        "version": "1.0.0",
        "status": "running",
    }


@app.get("/health")
async def health(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))

        database_status = "connected"

    except Exception:
        database_status = "disconnected"

    return {
        "status": "healthy",
        "database": database_status,
        "environment": settings.APP_ENV,
    }