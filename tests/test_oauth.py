import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select

from app.core.exceptions import AuthenticationError
from app.core.security import decode_access_token
from app.models.enums import OAuthProvider
from app.models.oauth_account import OAuthAccount
from app.models.user import User
from app.services.oauth_service import oauth_service

GOOGLE_REDIRECT_URI = "http://localhost:3000/auth/callback/google"
GITHUB_REDIRECT_URI = "http://localhost:3000/auth/callback/github"


def _mock_response(
    json_data: dict | list,
    *,
    status_code: int = 200,
    text: str | None = None,
) -> MagicMock:
    response = MagicMock()
    response.status_code = status_code
    response.is_error = status_code >= 400
    response.text = text if text is not None else str(json_data)
    response.json.return_value = json_data
    return response


@pytest.fixture
def oauth_settings():
    with patch("app.services.oauth_service.settings") as mock_settings:
        mock_settings.google_client_id = "google-client-id"
        mock_settings.google_client_secret = "google-client-secret"
        mock_settings.github_client_id = "github-client-id"
        mock_settings.github_client_secret = "github-client-secret"
        mock_settings.oauth_allowed_redirect_uris = [
            GOOGLE_REDIRECT_URI,
            GITHUB_REDIRECT_URI,
        ]
        yield mock_settings


@pytest.fixture
def mock_oauth_http():
    with patch("app.services.oauth_service.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__.return_value = mock_client
        mock_client_cls.return_value.__aexit__.return_value = None
        yield mock_client


def _configure_google_http(mock_client: AsyncMock) -> None:
    mock_client.post.return_value = _mock_response({"access_token": "google-access-token"})
    mock_client.get.return_value = _mock_response(
        {
            "sub": "google-sub-123",
            "email": "oauth-user@example.com",
            "email_verified": True,
            "name": "OAuth User",
        }
    )


def _configure_github_http(
    mock_client: AsyncMock,
    *,
    user_email: str | None = None,
    emails: list[dict] | None = None,
) -> None:
    async def get_side_effect(url: str, headers: dict | None = None):
        if url.endswith("/user"):
            return _mock_response(
                {
                    "id": 424242,
                    "login": "oauth-user",
                    "name": "OAuth User",
                    "email": user_email,
                }
            )
        if url.endswith("/user/emails"):
            return _mock_response(emails or [])
        raise AssertionError(f"Unexpected GET {url}")

    mock_client.post.return_value = _mock_response({"access_token": "github-access-token"})
    mock_client.get.side_effect = get_side_effect


@pytest.mark.asyncio
async def test_exchange_google_code_unverified_email_raises(oauth_settings, mock_oauth_http):
    mock_oauth_http.post.return_value = _mock_response({"access_token": "google-access-token"})
    mock_oauth_http.get.return_value = _mock_response(
        {
            "sub": "google-sub-123",
            "email": "oauth-user@example.com",
            "email_verified": False,
            "name": "OAuth User",
        }
    )

    with pytest.raises(AuthenticationError, match="not verified"):
        await oauth_service.exchange_google_code("auth-code", GOOGLE_REDIRECT_URI)


@pytest.mark.asyncio
async def test_exchange_google_code_invalid_redirect_uri_raises(oauth_settings):
    with pytest.raises(AuthenticationError, match="Invalid redirect URI"):
        await oauth_service.exchange_google_code("auth-code", "https://evil.example/callback")


@pytest.mark.asyncio
async def test_exchange_github_code_uses_emails_api_fallback(oauth_settings, mock_oauth_http):
    _configure_github_http(
        mock_oauth_http,
        user_email=None,
        emails=[
            {"email": "hidden@users.noreply.github.com", "primary": False, "verified": True},
            {"email": "primary@example.com", "primary": True, "verified": True},
        ],
    )

    profile = await oauth_service.exchange_github_code("auth-code", GITHUB_REDIRECT_URI)

    assert profile.email == "primary@example.com"
    assert profile.provider_user_id == "424242"


def test_google_oauth_new_user_returns_jwt(
    api_client,
    jwt_settings,
    oauth_settings,
    mock_oauth_http,
    sync_session,
):
    _configure_google_http(mock_oauth_http)
    email = f"google-new-{uuid.uuid4()}@example.com"
    mock_oauth_http.get.return_value = _mock_response(
        {
            "sub": f"google-sub-{uuid.uuid4()}",
            "email": email,
            "email_verified": True,
            "name": "Google New User",
        }
    )

    response = api_client.post(
        "/api/v1/auth/google/token",
        json={"code": "auth-code", "redirect_uri": GOOGLE_REDIRECT_URI},
    )

    assert response.status_code == 200
    body = response.json()
    user_id = decode_access_token(body["access_token"])

    user = sync_session.get(User, user_id)
    assert user is not None
    assert user.email == email
    assert user.password_hash is None

    oauth_account = sync_session.scalar(
        select(OAuthAccount).where(
            OAuthAccount.user_id == user_id,
            OAuthAccount.provider == OAuthProvider.GOOGLE.value,
        )
    )
    assert oauth_account is not None


def test_google_oauth_auto_links_existing_password_user(
    api_client,
    jwt_settings,
    oauth_settings,
    mock_oauth_http,
    test_user_with_password,
    sync_session,
):
    user, password = test_user_with_password
    provider_user_id = f"google-sub-{uuid.uuid4()}"
    _configure_google_http(mock_oauth_http)
    mock_oauth_http.get.return_value = _mock_response(
        {
            "sub": provider_user_id,
            "email": user.email,
            "email_verified": True,
            "name": user.name,
        }
    )

    response = api_client.post(
        "/api/v1/auth/google/token",
        json={"code": "auth-code", "redirect_uri": GOOGLE_REDIRECT_URI},
    )
    assert response.status_code == 200
    assert decode_access_token(response.json()["access_token"]) == user.id

    oauth_account = sync_session.scalar(
        select(OAuthAccount).where(
            OAuthAccount.user_id == user.id,
            OAuthAccount.provider == OAuthProvider.GOOGLE.value,
        )
    )
    assert oauth_account is not None
    assert oauth_account.provider_user_id == provider_user_id

    login_response = api_client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": password},
    )
    assert login_response.status_code == 200


def test_google_oauth_returning_user_returns_same_id(
    api_client,
    jwt_settings,
    oauth_settings,
    mock_oauth_http,
    sync_session,
):
    provider_user_id = f"google-sub-{uuid.uuid4()}"
    email = f"google-returning-{uuid.uuid4()}@example.com"
    _configure_google_http(mock_oauth_http)
    mock_oauth_http.get.return_value = _mock_response(
        {
            "sub": provider_user_id,
            "email": email,
            "email_verified": True,
            "name": "Returning User",
        }
    )

    first = api_client.post(
        "/api/v1/auth/google/token",
        json={"code": "auth-code-1", "redirect_uri": GOOGLE_REDIRECT_URI},
    )
    assert first.status_code == 200
    first_user_id = decode_access_token(first.json()["access_token"])

    second = api_client.post(
        "/api/v1/auth/google/token",
        json={"code": "auth-code-2", "redirect_uri": GOOGLE_REDIRECT_URI},
    )
    assert second.status_code == 200
    second_user_id = decode_access_token(second.json()["access_token"])

    assert first_user_id == second_user_id
    oauth_count = sync_session.scalar(
        select(OAuthAccount).where(OAuthAccount.provider_user_id == provider_user_id)
    )
    assert oauth_count is not None


def test_google_oauth_invalid_redirect_uri_returns_401(
    api_client,
    jwt_settings,
    oauth_settings,
    mock_oauth_http,
):
    response = api_client.post(
        "/api/v1/auth/google/token",
        json={"code": "auth-code", "redirect_uri": "https://evil.example/callback"},
    )
    assert response.status_code == 401
    assert response.json()["code"] == "authentication_error"


def test_github_oauth_new_user_returns_jwt(
    api_client,
    jwt_settings,
    oauth_settings,
    mock_oauth_http,
    sync_session,
):
    email = f"github-new-{uuid.uuid4()}@example.com"
    _configure_github_http(mock_oauth_http, user_email=email)

    response = api_client.post(
        "/api/v1/auth/github/token",
        json={"code": "auth-code", "redirect_uri": GITHUB_REDIRECT_URI},
    )

    assert response.status_code == 200
    user_id = decode_access_token(response.json()["access_token"])
    user = sync_session.get(User, user_id)
    assert user is not None
    assert user.email == email
    assert user.password_hash is None
