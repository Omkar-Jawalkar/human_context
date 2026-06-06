import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.exceptions import LLMError, RateLimitError
from app.models.chat_message import ChatMessage
from app.models.chat_thread import ChatThread
from app.models.enums import ChatMessageRole
from app.models.embedding import EmbeddingRecord
from app.models.user import User
from app.services.chat_service import ChatService
from app.services.llm_service import ContextUserProfile
from app.services.search_service import SearchHit


@pytest.fixture(autouse=True)
def _mock_chat_rate_limit():
    with patch(
        "app.services.chat_service.rate_limit_service.assert_chat_send_allowed",
        new=AsyncMock(),
    ):
        yield


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


def _make_thread(
    *,
    use_thread_history: bool = False,
    context_user_id: uuid.UUID | None = None,
) -> ChatThread:
    owner_id = uuid.uuid4()
    return ChatThread(
        id=uuid.uuid4(),
        user_id=owner_id,
        context_user_id=context_user_id or owner_id,
        organization_id=None,
        title="Test",
        use_thread_history=use_thread_history,
    )


def _make_context_user(thread: ChatThread) -> User:
    return User(
        id=thread.context_user_id,
        email="ctx@example.com",
        name="Context User",
        organization_id=None,
    )


@pytest.mark.asyncio
@patch("app.services.chat_service.context_access_service")
@patch("app.services.chat_service.llm_service")
@patch("app.services.chat_service.search_service")
async def test_send_message_always_searches_context_user(
    mock_search_service,
    mock_llm_service,
    mock_context_access,
):
    hits = [_make_hit("imported fact", 0.1)]
    mock_search_service.search_similar_messages = AsyncMock(return_value=hits)
    mock_llm_service.generate_chat_reply.return_value = "Reply"
    mock_context_access.assert_can_access_user_context = AsyncMock(
        return_value=_make_context_user(_make_thread())
    )
    mock_context_access.user_has_imported_conversations = AsyncMock(return_value=True)

    service = ChatService()
    db = AsyncMock()
    thread = _make_thread(use_thread_history=False)
    caller = User(
        id=thread.user_id,
        email="caller@example.com",
        name="Caller",
        organization_id=None,
    )

    db.scalar = AsyncMock(side_effect=[thread, 0])
    db.get = AsyncMock(return_value=caller)
    db.scalars = AsyncMock(return_value=MagicMock(all=MagicMock(return_value=[])))

    await service.send_message(db, thread.id, thread.user_id, "Hi")

    mock_search_service.search_similar_messages.assert_awaited_once()
    assert (
        mock_search_service.search_similar_messages.call_args.args[2]
        == thread.context_user_id
    )


@pytest.mark.asyncio
@patch("app.services.chat_service.context_access_service")
@patch("app.services.chat_service.llm_service")
@patch("app.services.chat_service.search_service")
async def test_send_message_no_imports_returns_canned_reply(
    mock_search_service,
    mock_llm_service,
    mock_context_access,
):
    thread = _make_thread()
    mock_context_access.assert_can_access_user_context = AsyncMock(
        return_value=_make_context_user(thread)
    )
    mock_context_access.user_has_imported_conversations = AsyncMock(return_value=False)

    service = ChatService()
    db = AsyncMock()
    caller = User(
        id=thread.user_id,
        email="caller@example.com",
        name="Caller",
        organization_id=None,
    )

    db.scalar = AsyncMock(side_effect=[thread, 0])
    db.get = AsyncMock(return_value=caller)

    result = await service.send_message(db, thread.id, thread.user_id, "Hi")

    assert result is not None
    assert "has not imported any Claude conversations" in result.assistant_message.content
    mock_search_service.search_similar_messages.assert_not_called()
    mock_llm_service.generate_chat_reply.assert_not_called()


@pytest.mark.asyncio
@patch("app.services.chat_service.context_access_service")
@patch("app.services.chat_service.llm_service")
@patch("app.services.chat_service.search_service")
async def test_send_message_use_thread_history_includes_prior_messages(
    mock_search_service,
    mock_llm_service,
    mock_context_access,
):
    mock_search_service.search_similar_messages = AsyncMock(return_value=[])
    mock_llm_service.generate_chat_reply.return_value = "Reply"
    thread = _make_thread(use_thread_history=True)
    mock_context_access.assert_can_access_user_context = AsyncMock(
        return_value=_make_context_user(thread)
    )
    mock_context_access.user_has_imported_conversations = AsyncMock(return_value=True)

    service = ChatService()
    db = AsyncMock()
    thread_id = thread.id
    caller = User(
        id=thread.user_id,
        email="caller@example.com",
        name="Caller",
        organization_id=None,
    )

    prior = [
        ChatMessage(
            thread_id=thread_id,
            role=ChatMessageRole.USER.value,
            content=f"msg-{index}",
            sequence=index,
        )
        for index in range(1, 8)
    ]

    db.scalar = AsyncMock(side_effect=[thread, 7])
    db.get = AsyncMock(return_value=caller)
    db.scalars = AsyncMock(
        return_value=MagicMock(
            all=MagicMock(return_value=list(reversed(prior[-5:])))
        )
    )

    await service.send_message(db, thread_id, thread.user_id, "latest")

    call_kwargs = mock_llm_service.generate_chat_reply.call_args.kwargs
    assert call_kwargs["thread_messages"] == [
        ("user", "msg-3"),
        ("user", "msg-4"),
        ("user", "msg-5"),
        ("user", "msg-6"),
        ("user", "msg-7"),
    ]


@pytest.mark.asyncio
@patch("app.services.chat_service.context_access_service")
@patch("app.services.chat_service.llm_service")
@patch("app.services.chat_service.search_service")
async def test_send_message_without_thread_history_sends_empty_history(
    mock_search_service,
    mock_llm_service,
    mock_context_access,
):
    mock_search_service.search_similar_messages = AsyncMock(return_value=[])
    mock_llm_service.generate_chat_reply.return_value = "Reply"
    thread = _make_thread(use_thread_history=False)
    mock_context_access.assert_can_access_user_context = AsyncMock(
        return_value=_make_context_user(thread)
    )
    mock_context_access.user_has_imported_conversations = AsyncMock(return_value=True)

    service = ChatService()
    db = AsyncMock()
    caller = User(
        id=thread.user_id,
        email="caller@example.com",
        name="Caller",
        organization_id=None,
    )

    db.scalar = AsyncMock(side_effect=[thread, 0])
    db.get = AsyncMock(return_value=caller)

    await service.send_message(db, thread.id, thread.user_id, "latest")

    call_kwargs = mock_llm_service.generate_chat_reply.call_args.kwargs
    assert call_kwargs["thread_messages"] == []
    assert call_kwargs["context_user"] == ContextUserProfile(
        id=thread.context_user_id, name="Context User"
    )


@pytest.mark.asyncio
@patch("app.services.chat_service.rate_limit_service")
async def test_send_message_calls_rate_limit_before_thread_lookup(mock_rate_limit):
    service = ChatService()
    db = AsyncMock()
    user_id = uuid.uuid4()
    mock_rate_limit.assert_chat_send_allowed = AsyncMock(
        side_effect=RateLimitError(
            "Chat message limit reached (20 per 6 hours).",
            retry_after_seconds=120,
        )
    )

    with pytest.raises(RateLimitError):
        await service.send_message(db, uuid.uuid4(), user_id, "Hello")

    mock_rate_limit.assert_chat_send_allowed.assert_awaited_once_with(user_id)
    db.scalar.assert_not_called()


@pytest.mark.asyncio
async def test_send_message_wrong_owner_returns_none():
    service = ChatService()
    db = AsyncMock()
    db.scalar = AsyncMock(return_value=None)

    result = await service.send_message(
        db, uuid.uuid4(), uuid.uuid4(), "Hello"
    )

    assert result is None


@pytest.mark.asyncio
async def test_send_message_empty_content_raises():
    service = ChatService()
    db = AsyncMock()

    with pytest.raises(LLMError, match="Message must not be empty"):
        await service.send_message(db, uuid.uuid4(), uuid.uuid4(), "   ")
