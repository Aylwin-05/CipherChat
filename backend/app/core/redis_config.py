import logging

from app.core.config import settings

logger = logging.getLogger("app.core.redis_config")


def get_redis_pubsub_config() -> dict:
    if not settings.REDIS_URL:
        return {"enabled": False}

    return {
        "enabled": True,
        "url": settings.REDIS_URL,
        "fanout_channel": "nexara:ws:fanout",
        "max_connections": 20,
        "socket_connect_timeout": 3,
        "socket_timeout": 3,
    }


def get_uvicorn_worker_count() -> int:
    import os

    env_val = os.environ.get("WEB_CONCURRENCY")
    if env_val:
        try:
            return max(1, int(env_val))
        except ValueError:
            pass

    cpu_count = os.cpu_count() or 1
    return max(1, cpu_count)


def get_uvicorn_config() -> dict:
    workers = get_uvicorn_worker_count()
    return {
        "host": "0.0.0.0",
        "port": 8000,
        "workers": workers,
        "loop": "uvloop",
        "http": "httptools",
        "proxy_headers": True,
        "forwarded_allow_ips": "*",
        "access_log": False,
        "log_level": settings.LOG_LEVEL.lower(),
    }
