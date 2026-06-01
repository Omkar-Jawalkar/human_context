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
    SearchError,
)


def _status_code_for_error(exc: AppError) -> int:
    if isinstance(exc, AuthenticationError):
        return 401
    if isinstance(exc, AuthorizationError):
        return 403
    if isinstance(exc, ConflictError):
        return 409
    if isinstance(exc, ConfigurationError):
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


async def app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=_status_code_for_error(exc),
        content={"detail": exc.message, "code": exc.code},
    )
