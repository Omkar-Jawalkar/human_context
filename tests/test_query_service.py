import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.exceptions import ConfigurationError
from app.models.embedding import EmbeddingRecord
from app.models.user import User
from app.services.llm_service import ContextUserProfile, LLMService
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


def _make_target_user() -> User:
    return User(
        id=uuid.uuid4(),
        email="target@example.com",
        name="Target User",
        organization_id=None,
    )


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
@patch("app.services.query_service.context_access_service")
@patch("app.services.query_service.llm_service")
@patch("app.services.query_service.search_service")
async def test_answer_query_omits_sources_when_not_development(
    mock_search_service,
    mock_llm_service,
    mock_context_access,
):
    hits = [_make_hit("context one", 0.1)]
    mock_search_service.search_similar_messages = AsyncMock(return_value=hits)
    mock_llm_service.generate_answer.return_value = "Generated answer"
    mock_context_access.user_has_imported_conversations = AsyncMock(return_value=True)

    service = QueryService()
    db = AsyncMock()
    target_user = _make_target_user()

    result = await service.answer_query(
        db,
        "What happened?",
        target_user,
        is_development=False,
    )

    assert result.answer == "Generated answer"
    assert result.sources is None
    mock_search_service.search_similar_messages.assert_awaited_once_with(
        db, "What happened?", target_user.id, limit=5
    )
    mock_llm_service.generate_answer.assert_called_once_with(
        "What happened?",
        ["context one"],
        context_user=ContextUserProfile(id=target_user.id, name=target_user.name),
    )


@pytest.mark.asyncio
@patch("app.services.query_service.context_access_service")
@patch("app.services.query_service.llm_service")
@patch("app.services.query_service.search_service")
async def test_answer_query_includes_sources_when_development(
    mock_search_service,
    mock_llm_service,
    mock_context_access,
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
    mock_context_access.user_has_imported_conversations = AsyncMock(return_value=True)

    service = QueryService()
    db = AsyncMock()
    target_user = _make_target_user()

    result = await service.answer_query(
        db,
        "What happened?",
        target_user,
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
@patch("app.services.query_service.context_access_service")
@patch("app.services.query_service.llm_service")
@patch("app.services.query_service.search_service")
async def test_answer_query_no_imports_returns_canned_reply(
    mock_search_service,
    mock_llm_service,
    mock_context_access,
):
    mock_context_access.user_has_imported_conversations = AsyncMock(return_value=False)

    service = QueryService()
    db = AsyncMock()
    target_user = _make_target_user()

    result = await service.answer_query(db, "What happened?", target_user)

    assert "has not imported any Claude conversations" in result.answer
    mock_search_service.search_similar_messages.assert_not_called()
    mock_llm_service.generate_answer.assert_not_called()


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


@patch("app.services.llm_service.settings")
def test_generate_chat_reply_builds_multi_turn_messages(mock_settings):
    mock_settings.openai_api_key = "test-key"
    mock_settings.openai_chat_model = "gpt-4.1"

    service = LLMService()
    context_user = ContextUserProfile(id=uuid.uuid4(), name="Bob")
    with patch(
        "app.services.llm_service.post_openai",
        return_value={"choices": [{"message": {"content": "Sure thing."}}]},
    ) as post_openai:
        answer = service.generate_chat_reply(
            thread_messages=[("user", "Earlier question"), ("assistant", "Earlier answer")],
            user_message="Follow up",
            context_user=context_user,
            rag_contexts=["Imported snippet"],
        )

    assert answer == "Sure thing."
    payload = post_openai.call_args.kwargs["json_body"]
    roles = [message["role"] for message in payload["messages"]]
    assert roles == ["system", "user", "assistant", "user", "assistant", "user"]
    assert "Bob's imported Claude history" in payload["messages"][1]["content"]
    assert "[1] Imported snippet" in payload["messages"][1]["content"]
    assert "responding as Bob" in payload["messages"][0]["content"]
    assert payload["messages"][-1]["content"] == "Follow up"
