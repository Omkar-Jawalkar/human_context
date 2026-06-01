import uuid
from datetime import timedelta
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.core.exceptions import AuthenticationError, ConfigurationError
from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from app.main import app

client = TestClient(app)


def test_hash_and_verify_password():
    hashed = hash_password("secret123")
    assert hashed != "secret123"
    assert verify_password("secret123", hashed)
    assert not verify_password("wrong", hashed)


def test_create_and_decode_access_token(jwt_settings):
    user_id = uuid.uuid4()
    token = create_access_token(user_id)
    assert decode_access_token(token) == user_id


def test_decode_access_token_invalid_raises_authentication_error(jwt_settings):
    with pytest.raises(AuthenticationError, match="Invalid or expired token"):
        decode_access_token("not-a-valid-token")


def test_decode_access_token_expired_raises_authentication_error(jwt_settings):
    user_id = uuid.uuid4()
    token = create_access_token(user_id, expires_delta=timedelta(seconds=-1))
    with pytest.raises(AuthenticationError, match="Invalid or expired token"):
        decode_access_token(token)


def test_create_access_token_missing_secret_raises_configuration_error():
    with patch("app.core.security.settings") as mock_settings:
        mock_settings.jwt_secret_key = None
        with pytest.raises(ConfigurationError, match="JWT_SECRET_KEY is required"):
            create_access_token(uuid.uuid4())


def test_protected_route_without_token_returns_401():
    response = client.post("/api/v1/tasks", json={"message": "hello"})
    assert response.status_code == 401


def test_login_invalid_credentials_returns_401(jwt_settings, test_user_with_password):
    user, _password = test_user_with_password
    response = client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": "wrong-password"},
    )
    assert response.status_code == 401
    assert response.json()["code"] == "authentication_error"


def test_login_success_returns_token(jwt_settings, test_user_with_password):
    user, password = test_user_with_password
    response = client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": password},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert decode_access_token(body["access_token"]) == user.id


def test_protected_route_with_valid_token_returns_200(
    jwt_settings, auth_headers, override_current_user
):
    response = client.post(
        "/api/v1/tasks",
        json={"message": "hello"},
        headers=auth_headers,
    )
    assert response.status_code == 202


@patch("app.api.v1.endpoints.query.query_service.answer_query", new_callable=AsyncMock)
def test_query_uses_target_user_id_from_body(
    mock_answer_query,
    jwt_settings,
    auth_headers,
    override_current_user,
):
    from unittest.mock import AsyncMock

    from app.api.deps import get_db
    from app.main import app
    from app.models.user import User
    from app.services.query_service import QueryResult

    caller = override_current_user
    target_user = User(
        id=uuid.uuid4(),
        organization_id=caller.organization_id,
        email="target@example.com",
        name="Target User",
    )

    mock_db = AsyncMock()

    async def fake_get(model, pk):
        if pk == target_user.id:
            return target_user
        return None

    mock_db.get = fake_get

    async def override_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_get_db
    mock_answer_query.return_value = QueryResult(answer="ok", sources=None)

    try:
        response = client.post(
            "/api/v1/query",
            json={"query": "hello", "user_id": str(target_user.id)},
            headers=auth_headers,
        )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200
    mock_answer_query.assert_called_once()
    call_args = mock_answer_query.call_args
    assert call_args[0][2] == target_user.id
    assert call_args[0][2] != caller.id
