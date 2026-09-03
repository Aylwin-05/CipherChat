from app.core.rate_limit import (
    RateLimitExceeded,
    get_limiter,
)
from fastapi import Depends, HTTPException, Request


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
    # NOTE: the reverse proxy (nginx) OVERWRITES X-Forwarded-For
    # with $remote_addr, so the first entry is the real client.
    # The header is only honored when it contains a valid IP;
    # garbage or absent values fall back to the direct peer.
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        candidate = forwarded.split(",")[0].strip()
        if _is_ip(candidate):
            return candidate
    return request.client.host if request.client else "unknown"


def _is_ip(value: str) -> bool:
    try:
        import ipaddress
        ipaddress.ip_address(value)
        return True
    except ValueError:
        return False
