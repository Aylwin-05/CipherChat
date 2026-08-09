from fastapi import Depends, HTTPException, Request

from app.core.rate_limit import (
    RateLimitExceeded,
    get_limiter,
)


def rate_limit(
    key: str,
    limit: int,
    window: int,
):
    """
    Dependency factory: rejects requests that exceed `limit`
    hits per `window` seconds, keyed by `key` + client IP.

    Returns an HTTPException (429) with a Retry-After header,
    so a route can declare it as:

        dependencies=[rate_limit("messages.send.ip", 60, 60)],
    """

    async def dependency(request: Request):
        limiter = get_limiter()
        try:
            await limiter.check(
                f"{key}.{_client_ip(request)}",
                limit,
                window,
            )
        except RateLimitExceeded as exc:
            raise HTTPException(
                status_code=429,
                detail="Too many requests. Try again later.",
                headers={"Retry-After": str(exc.retry_after)},
            )

    return Depends(dependency)


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"