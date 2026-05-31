"""Application exception hierarchy for service and API layers."""


class AppError(Exception):
    """Base exception for expected application failures."""

    code: str = "app_error"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class ConfigurationError(AppError):
    """Missing or invalid application configuration."""

    code = "configuration_error"


class OpenAIAPIError(AppError):
    """OpenAI HTTP or response parsing failure."""

    code = "openai_api_error"

    def __init__(
        self,
        message: str,
        *,
        operation: str,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.operation = operation
        self.status_code = status_code


class EmbeddingError(AppError):
    """Embedding generation or validation failure."""

    code = "embedding_error"


class LLMError(AppError):
    """LLM completion or response validation failure."""

    code = "llm_error"


class SearchError(AppError):
    """Vector search failure."""

    code = "search_error"
