# ==========================================================
# Security middleware
# ==========================================================

from fastapi import Request

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": (
        "camera=(), microphone=(), geolocation=()"
    ),
    "Cross-Origin-Opener-Policy": "same-origin",
}

CSP_HEADER = (
    "default-src 'self'; "
    "img-src 'self' data: blob:; "
    "media-src 'self' blob:; "
    "connect-src 'self' wss: ws:; "
    "style-src 'self' 'unsafe-inline'; "
    "script-src 'self'; "
    "font-src 'self' data:"
)


class SecurityHeadersMiddleware:
    """
    Adds hardening headers to every response.
    CSP stays modest so the SPA keeps working over the proxy.
    """

    def __init__(self, app, enable_csp: bool = True):
        self.app = app
        self.enable_csp = enable_csp

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                headers = message.get("headers", [])
                headers = [
                    (k.lower(), v)
                    for (k, v) in headers
                ]
                for name, value in SECURITY_HEADERS.items():
                    headers.append(
                        (name.lower().encode(), value.encode())
                    )
                if self.enable_csp:
                    headers.append(
                        (
                            b"content-security-policy",
                            CSP_HEADER.encode(),
                        )
                    )
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_wrapper)


class RequestIdMiddleware:
    """
    Give every request an ID, echo it back and log it.
    """

    def __init__(self, app, logger=None):
        self.app = app
        self.logger = logger

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive)
        request_id = request.headers.get(
            "x-request-id"
        )
        if not request_id:
            import uuid

            request_id = uuid.uuid4().hex[:16]

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                headers = message.get("headers", [])
                headers.append(
                    (b"x-request-id", request_id.encode())
                )
                message["headers"] = headers
            await send(message)

        if self.logger:
            self.logger.info(
                "%s %s -> request_id=%s",
                request.method,
                request.url.path,
                request_id,
            )

        await self.app(scope, receive, send_wrapper)