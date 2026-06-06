import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

from app.api.deps import get_db
from app.main import app
from app.models.chat_message import ChatMessage
from app.models.chat_thread import ChatThread
from app.models.enums import ChatMessageRole
from app.services.chat_service import SendMessageResult


def _mock_db_session():
    db = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()

    async def _override():
        yield db

    return db, _override


def test_chats_without_token_returns_401(api_client):
    response = api_client.post(
        "/api/v1/chats",
        json={
            "title": "Test",
            "context_user_id": str(uuid.uuid4()),
            "use_thread_history": False,
        },
    )
    assert response.status_code == 401


def test_create_and_send_message_flow(
    jwt_settings, auth_headers, override_current_user, api_client
):
    user = override_current_user
    now = datetime.now(UTC)
    context_user_id = user.id
    thread = ChatThread(
        id=uuid.uuid4(),
        user_id=user.id,
        context_user_id=context_user_id,
        organization_id=user.organization_id,
        title="My chat",
        use_thread_history=True,
        created_at=now,
        updated_at=now,
    )
    mock_db, db_override = _mock_db_session()
    app.dependency_overrides[get_db] = db_override
    user_message = ChatMessage(
        id=uuid.uuid4(),
        thread_id=thread.id,
        role=ChatMessageRole.USER.value,
        content="Hello",
        sequence=1,
        created_at=now,
    )
    assistant_message = ChatMessage(
        id=uuid.uuid4(),
        thread_id=thread.id,
        role=ChatMessageRole.ASSISTANT.value,
        content="Hi there",
        sequence=2,
        sources=None,
        created_at=now,
    )

    with patch(
        "app.api.v1.endpoints.chats.chat_service.create_thread",
        new=AsyncMock(return_value=thread),
    ):
        create_resp = api_client.post(
            "/api/v1/chats",
            json={
                "title": "My chat",
                "context_user_id": str(context_user_id),
                "use_thread_history": True,
            },
            headers=auth_headers,
        )

    assert create_resp.status_code == 201
    body = create_resp.json()
    assert body["title"] == "My chat"
    assert body["context_user_id"] == str(context_user_id)
    assert body["use_thread_history"] is True
    assert body["user_id"] == str(user.id)

    app.dependency_overrides[get_db] = db_override
    with patch(
        "app.api.v1.endpoints.chats.chat_service.send_message",
        new=AsyncMock(
            return_value=SendMessageResult(
                user_message=user_message,
                assistant_message=assistant_message,
            )
        ),
    ):
        send_resp = api_client.post(
            f"/api/v1/chats/{thread.id}/messages",
            json={"content": "Hello"},
            headers=auth_headers,
        )

    app.dependency_overrides.pop(get_db, None)
    assert send_resp.status_code == 200
    send_body = send_resp.json()
    assert send_body["user_message"]["content"] == "Hello"
    assert send_body["assistant_message"]["content"] == "Hi there"


def test_send_message_unknown_thread_returns_404(
    jwt_settings, auth_headers, override_current_user, api_client
):
    thread_id = uuid.uuid4()
    with patch(
        "app.api.v1.endpoints.chats.chat_service.send_message",
        new=AsyncMock(return_value=None),
    ):
        response = api_client.post(
            f"/api/v1/chats/{thread_id}/messages",
            json={"content": "Hello"},
            headers=auth_headers,
        )

    assert response.status_code == 404


def test_delete_unknown_thread_returns_404(
    jwt_settings, auth_headers, override_current_user, api_client
):
    thread_id = uuid.uuid4()
    with patch(
        "app.api.v1.endpoints.chats.chat_service.delete_thread",
        new=AsyncMock(return_value=False),
    ):
        response = api_client.delete(
            f"/api/v1/chats/{thread_id}",
            headers=auth_headers,
        )

    assert response.status_code == 404
