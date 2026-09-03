"""
Centralized exception hierarchy for Nexara.

Services raise typed domain exceptions; the global FastAPI
exception handler maps them to consistent JSON envelopes.
"""



class NexaraException(Exception):
    """Base class for all domain exceptions."""

    status_code: int = 500
    detail: str = "Internal server error."

    def __init__(self, detail: str | None = None):
        if detail is not None:
            self.detail = detail
        super().__init__(self.detail)


class NotFoundException(NexaraException):
    status_code = 404
    detail = "Resource not found."


class ForbiddenException(NexaraException):
    status_code = 403
    detail = "You do not have permission to perform this action."


class BadRequestException(NexaraException):
    status_code = 400
    detail = "Bad request."


class ConflictException(NexaraException):
    status_code = 409
    detail = "Resource already exists."


class RateLimitedException(NexaraException):
    status_code = 429
    detail = "Too many requests. Try again later."


class SessionExpiredException(NexaraException):
    status_code = 401
    detail = "Session has expired. Please log in again."
