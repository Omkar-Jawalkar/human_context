from datetime import UTC, datetime, timedelta

from fastapi import Request
from fastapi.responses import JSONResponse

from app.core.exceptions import (
    AppError,
    AuthenticationError,
    AuthorizationError,
    ConfigurationError,
    ConflictError,
    EmbeddingError,
    LLMError,
    OpenAIAPIError,
    RateLimitError,
    SearchError,
    ServiceUnavailableError,
)


def _status_code_for_error(exc: AppError) -> int:
    if isinstance(exc, AuthenticationError):
        return 401
    if isinstance(exc, AuthorizationError):
        return 403
    if isinstance(exc, ConflictError):
        return 409
    if isinstance(exc, RateLimitError):
        return 429
    if isinstance(exc, (ConfigurationError, ServiceUnavailableError)):
        return 503
    if isinstance(exc, OpenAIAPIError):
        if exc.status_code == 429:
            return 503
        if exc.status_code is not None and exc.status_code >= 500:
            return 502
        return 502
    if isinstance(exc, (EmbeddingError, LLMError, SearchError)):
        return 500
    return 500


def _format_utc_timestamp(value: datetime) -> str:
    return value.replace(microsecond=0).isoformat().replace("+00:00", "Z")


async def app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
    headers: dict[str, str] | None = None
    content: dict[str, str | int] = {"detail": exc.message, "code": exc.code}

    if isinstance(exc, RateLimitError) and exc.retry_after_seconds is not None:
        headers = {"Retry-After": str(exc.retry_after_seconds)}
        retry_at = datetime.now(UTC) + timedelta(seconds=exc.retry_after_seconds)
        content["retry_after_seconds"] = exc.retry_after_seconds
        content["retry_at"] = _format_utc_timestamp(retry_at)

    return JSONResponse(
        status_code=_status_code_for_error(exc),
        content=content,
        headers=headers,
    )
