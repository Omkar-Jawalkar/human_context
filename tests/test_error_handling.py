from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.core.exceptions import (
    ConfigurationError,
    EmbeddingError,
    LLMError,
    OpenAIAPIError,
)
from app.core.openai_http import post_openai
from app.services.embedding_service import EmbeddingService
from app.services.llm_service import LLMService


def test_post_openai_missing_api_key_raises_configuration_error():
    with pytest.raises(ConfigurationError, match="OPENAI_API_KEY is required"):
        post_openai(
            "embeddings",
            api_key=None,
            json_body={},
            timeout=10.0,
            operation="embeddings",
        )


@patch("app.core.openai_http.httpx.post")
def test_post_openai_http_error_raises_openai_api_error(mock_post):
    response = MagicMock()
    response.is_error = True
    response.status_code = 401
    response.text = "Unauthorized"
    response.json.return_value = {"error": {"message": "Invalid API key"}}
    mock_post.return_value = response

    with pytest.raises(OpenAIAPIError, match="Invalid API key") as exc_info:
        post_openai(
            "embeddings",
            api_key="test-key",
            json_body={"model": "text-embedding-3-small", "input": ["hi"]},
            timeout=10.0,
            operation="embeddings",
        )

    assert exc_info.value.status_code == 401


@patch("app.core.openai_http.httpx.post")
def test_post_openai_timeout_raises_openai_api_error(mock_post):
    mock_post.side_effect = httpx.TimeoutException("timed out")

    with pytest.raises(OpenAIAPIError, match="timed out"):
        post_openai(
            "chat/completions",
            api_key="test-key",
            json_body={},
            timeout=10.0,
            operation="chat completions",
        )


@patch("app.services.embedding_service.settings")
def test_embed_text_empty_raises_embedding_error(mock_settings):
    mock_settings.embedding_provider = "fake"
    service = EmbeddingService()
    with pytest.raises(EmbeddingError, match="empty text"):
        service.embed_text("   ")


@patch("app.services.embedding_service.settings")
def test_embed_openai_batch_dimension_mismatch_raises_embedding_error(mock_settings):
    mock_settings.embedding_provider = "openai"
    mock_settings.openai_api_key = "test-key"
    mock_settings.openai_embedding_model = "text-embedding-3-small"
    mock_settings.embedding_dimensions = 3

    with patch(
        "app.services.embedding_service.post_openai",
        return_value={"data": [{"index": 0, "embedding": [0.1, 0.2]}]},
    ):
        service = EmbeddingService()
        with pytest.raises(EmbeddingError, match="Expected 3 dimensions"):
            service.embed_texts(["only one"])


@patch("app.services.llm_service.settings")
def test_generate_answer_missing_api_key_raises_configuration_error(mock_settings):
    mock_settings.openai_api_key = None
    mock_settings.openai_chat_model = "gpt-4.1"
    service = LLMService()
    with pytest.raises(ConfigurationError, match="OPENAI_API_KEY is required"):
        service.generate_answer("hello", ["context"])


@patch("app.services.llm_service.settings")
def test_generate_answer_missing_choices_raises_llm_error(mock_settings):
    mock_settings.openai_api_key = "test-key"
    mock_settings.openai_chat_model = "gpt-4.1"

    with patch("app.services.llm_service.post_openai", return_value={"choices": []}):
        service = LLMService()
        with pytest.raises(LLMError, match="missing 'choices'"):
            service.generate_answer("hello", ["context"])
