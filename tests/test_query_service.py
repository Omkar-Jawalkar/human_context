import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.exceptions import ConfigurationError
from app.models.embedding import EmbeddingRecord
from app.services.llm_service import LLMService
from app.services.query_service import QueryService, query_service
from app.services.search_service import SearchHit, SearchService


def _make_hit(content: str, distance: float, metadata: dict | None = None) -> SearchHit:
    record = EmbeddingRecord(
        namespace="message:test",
        content=content,
        metadata_=metadata
        or {
            "message_id": str(uuid.uuid4()),
            "conversation_id": str(uuid.uuid4()),
            "sender": "human",
            "import_job_id": str(uuid.uuid4()),
        },
        embedding=[0.0] * 1536,
    )
    return SearchHit(record=record, distance=distance)


@patch("app.services.llm_service.settings")
def test_generate_answer_uses_gpt_model_and_context(mock_settings):
    mock_settings.openai_api_key = "test-key"
    mock_settings.openai_chat_model = "gpt-4.1"

    service = LLMService()
    with patch(
        "app.services.llm_service.post_openai",
        return_value={"choices": [{"message": {"content": "The answer is 42."}}]},
    ) as post_openai:
        answer = service.generate_answer(
            "What is the answer?",
            ["First context", "Second context"],
        )

    assert answer == "The answer is 42."
    post_openai.assert_called_once()
    payload = post_openai.call_args.kwargs["json_body"]
    assert payload["model"] == "gpt-4.1"
    user_content = payload["messages"][1]["content"]
    assert "[1] First context" in user_content
    assert "[2] Second context" in user_content
    assert "What is the answer?" in user_content


@patch("app.services.llm_service.settings")
def test_generate_answer_missing_api_key_raises(mock_settings):
    mock_settings.openai_api_key = None
    service = LLMService()
    with pytest.raises(ConfigurationError, match="OPENAI_API_KEY is required"):
        service.generate_answer("hello", ["context"])


@pytest.mark.asyncio
@patch("app.services.query_service.llm_service")
@patch("app.services.query_service.search_service")
async def test_answer_query_omits_sources_when_not_development(
    mock_search_service,
    mock_llm_service,
):
    hits = [_make_hit("context one", 0.1)]
    mock_search_service.search_similar_messages = AsyncMock(return_value=hits)
    mock_llm_service.generate_answer.return_value = "Generated answer"

    service = QueryService()
    db = AsyncMock()
    user_id = uuid.uuid4()

    result = await service.answer_query(
        db,
        "What happened?",
        user_id,
        is_development=False,
    )

    assert result.answer == "Generated answer"
    assert result.sources is None
    mock_search_service.search_similar_messages.assert_awaited_once_with(
        db, "What happened?", user_id, limit=5
    )
    mock_llm_service.generate_answer.assert_called_once_with(
        "What happened?",
        ["context one"],
    )


@pytest.mark.asyncio
@patch("app.services.query_service.llm_service")
@patch("app.services.query_service.search_service")
async def test_answer_query_includes_sources_when_development(
    mock_search_service,
    mock_llm_service,
):
    metadata = {
        "message_id": "msg-1",
        "conversation_id": "conv-1",
        "sender": "assistant",
        "import_job_id": "job-1",
    }
    hits = [
        _make_hit("first", 0.1, metadata),
        _make_hit("second", 0.2, metadata),
    ]
    mock_search_service.search_similar_messages = AsyncMock(return_value=hits)
    mock_llm_service.generate_answer.return_value = "Generated answer"

    service = QueryService()
    db = AsyncMock()
    user_id = uuid.uuid4()

    result = await service.answer_query(
        db,
        "What happened?",
        user_id,
        is_development=True,
    )

    assert result.answer == "Generated answer"
    assert result.sources is not None
    assert len(result.sources) == 2
    assert result.sources[0].content == "first"
    assert result.sources[0].distance == 0.1
    assert result.sources[0].message_id == "msg-1"
    assert result.sources[0].conversation_id == "conv-1"
    assert result.sources[0].sender == "assistant"
    assert result.sources[0].import_job_id == "job-1"


@pytest.mark.asyncio
@patch("app.services.search_service.embedding_service")
async def test_search_similar_messages_orders_by_distance(mock_embedding_service):
    user_id = uuid.uuid4()
    query_vec = [0.1, 0.2, 0.3]
    mock_embedding_service.embed_text.return_value = query_vec

    hit_a = _make_hit("a", 0.05)
    hit_b = _make_hit("b", 0.15)

    service = SearchService()
    db = AsyncMock()
    db.execute = AsyncMock(
        return_value=MagicMock(
            all=MagicMock(return_value=[(hit_a.record, 0.05), (hit_b.record, 0.15)])
        )
    )

    with patch(
        "app.services.search_service.asyncio.to_thread",
        new=AsyncMock(return_value=query_vec),
    ):
        results = await service.search_similar_messages(db, "search me", user_id, limit=5)

    assert len(results) == 2
    assert results[0].distance == 0.05
    assert results[1].distance == 0.15
    db.execute.assert_awaited_once()


def test_query_service_singleton():
    assert query_service is not None
