from unittest.mock import patch

import pytest

from app.core.config import settings
from app.core.exceptions import EmbeddingError
from app.services.embedding_service import EmbeddingService, embedding_service


def test_embed_texts_empty():
    assert embedding_service.embed_texts([]) == []


@patch("app.services.embedding_service.settings")
def test_embedding_service_fake_provider_dimensions(mock_settings):
    mock_settings.embedding_provider = "fake"
    mock_settings.embedding_dimensions = settings.embedding_dimensions
    service = EmbeddingService()
    vectors = service.embed_texts(["hello world", "other"])
    assert len(vectors) == 2
    assert all(len(vector) == settings.embedding_dimensions for vector in vectors)


@patch("app.services.embedding_service.settings")
def test_embed_text_matches_batch_first_item(mock_settings):
    mock_settings.embedding_provider = "fake"
    mock_settings.embedding_dimensions = settings.embedding_dimensions
    service = EmbeddingService()
    single = service.embed_text("hello world")
    batch = service.embed_texts(["hello world"])
    assert single == batch[0]


@patch("app.services.embedding_service.settings")
def test_embed_texts_parallel_fake_provider(mock_settings):
    mock_settings.embedding_provider = "fake"
    mock_settings.embedding_dimensions = settings.embedding_dimensions
    service = EmbeddingService()
    texts = ["a", "b", "c"]
    sequential = service.embed_texts(texts)
    parallel = service.embed_texts_parallel(texts, batch_size=2, max_workers=4)
    assert parallel == sequential


@patch("app.services.embedding_service.settings")
def test_embed_openai_batch_request_and_order(mock_settings):
    mock_settings.embedding_provider = "openai"
    mock_settings.openai_api_key = "test-key"
    mock_settings.openai_embedding_model = "text-embedding-3-small"
    mock_settings.embedding_dimensions = 3

    service = EmbeddingService()
    with patch(
        "app.services.embedding_service.post_openai",
        return_value={
            "data": [
                {"index": 1, "embedding": [0.1, 0.2, 0.3]},
                {"index": 0, "embedding": [0.4, 0.5, 0.6]},
            ]
        },
    ) as post_openai:
        result = service.embed_texts(["first", "second"])

    post_openai.assert_called_once()
    assert post_openai.call_args.kwargs["json_body"]["input"] == ["first", "second"]
    assert result == [[0.4, 0.5, 0.6], [0.1, 0.2, 0.3]]


@patch("app.services.embedding_service.settings")
def test_embed_openai_batch_dimension_mismatch_raises(mock_settings):
    mock_settings.embedding_provider = "openai"
    mock_settings.openai_api_key = "test-key"
    mock_settings.openai_embedding_model = "text-embedding-3-small"
    mock_settings.embedding_dimensions = 3

    service = EmbeddingService()
    with patch(
        "app.services.embedding_service.post_openai",
        return_value={"data": [{"index": 0, "embedding": [0.1, 0.2]}]},
    ):
        with pytest.raises(EmbeddingError, match="Expected 3 dimensions"):
            service.embed_texts(["only one"])


@patch("app.services.embedding_service.settings")
def test_embed_openai_batch_count_mismatch_raises(mock_settings):
    mock_settings.embedding_provider = "openai"
    mock_settings.openai_api_key = "test-key"
    mock_settings.openai_embedding_model = "text-embedding-3-small"
    mock_settings.embedding_dimensions = 3

    service = EmbeddingService()
    with patch("app.services.embedding_service.post_openai", return_value={"data": []}):
        with pytest.raises(EmbeddingError, match="Expected 2 embeddings"):
            service.embed_texts(["a", "b"])
