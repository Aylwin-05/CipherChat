import logging

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.api import api_router
from app.core.config import settings
from app.core.logging import setup_logging
from app.core.middleware import (
    RequestIdMiddleware,
    SecurityHeadersMiddleware,
)
from app.database.session import get_db
from app.websocket.ws import router as websocket_router

setup_logging()

logger = logging.getLogger("app.main")

app = FastAPI(
    title=settings.APP_NAME,
    description="CipherChat Backend API",
    version="1.0.0",
    debug=settings.DEBUG,
    redirect_slashes=False,
    contact={
        "name": "CipherChat API",
        "email": settings.SMTP_FROM_EMAIL,
    },
    license_info={
        "name": "MIT",
    },
)

# ==========================================================
# CORS (env-driven)
# ==========================================================

origins = [
    origin.strip()
    for origin in settings.CORS_ORIGINS.split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==========================================================
# Host validation + hardening
# ==========================================================

app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=[
        host.strip()
        for host in settings.ALLOWED_HOSTS.split(",")
        if host.strip()
    ],
)

app.add_middleware(
    SecurityHeadersMiddleware,
    enable_csp=not settings.DEBUG,
)

app.add_middleware(
    RequestIdMiddleware,
    logger=logger,
)

# ==========================================================
# Global Exception Handlers (always JSON, never plain text)
# ==========================================================


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
):
    errors = [
        {
            "field": ".".join(
                str(part) for part in error["loc"][1:]
            ),
            "message": error["msg"],
        }
        for error in exc.errors()
    ]

    request_id = request.state.request_id

    return JSONResponse(
        status_code=422,
        content={
            "detail": "Invalid request.",
            "errors": errors,
            "request_id": request_id,
        },
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(
    request: Request,
    exc: Exception,
):
    logger.exception(
        "Unhandled exception on %s %s: %s",
        request.method,
        request.url.path,
        exc,
    )

    error_response = JSONResponse(
        status_code=500,
        content={
            "detail": "Internal server error.",
            "request_id": getattr(
                request.state,
                "request_id",
                None,
            ),
        },
    )

    if settings.DEBUG:
        error_response = JSONResponse(
            status_code=500,
            content={
                "detail": "Internal server error.",
                "error": repr(exc),
                "request_id": getattr(
                    request.state,
                    "request_id",
                    None,
                ),
            },
        )

    return error_response

# ==========================================================
# REST API Routes
# ==========================================================

app.include_router(
    api_router,
    prefix="/api/v1",
)

# ==========================================================
# WebSocket Routes
# ==========================================================

app.include_router(
    websocket_router,
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
        "health": "/health",
        "websocket": "/ws/me",
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
        logger.error("Health check failed: %s", e)
        database_status = "disconnected"

    return {
        "status": "healthy",
        "database": database_status,
        "environment": settings.APP_ENV,
    }