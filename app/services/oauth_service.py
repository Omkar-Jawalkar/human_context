from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import AuthenticationError, ConfigurationError, ConflictError
from app.models.enums import OAuthProvider
from app.models.oauth_account import OAuthAccount
from app.models.user import User

logger = logging.getLogger(__name__)

GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_USER_URL = "https://api.github.com/user"
GITHUB_EMAILS_URL = "https://api.github.com/user/emails"
OAUTH_HTTP_TIMEOUT = 30.0


@dataclass(frozen=True)
class OAuthProfile:
    provider_user_id: str
    email: str
    name: str


class OAuthService:
    def assert_redirect_uri_allowed(self, redirect_uri: str) -> None:
        if redirect_uri not in settings.oauth_allowed_redirect_uris:
            raise AuthenticationError("Invalid redirect URI")

    def _assert_google_configured(self) -> None:
        if not settings.google_client_id or not settings.google_client_secret:
            raise ConfigurationError(
                "GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET are required for Google OAuth"
            )

    def _assert_github_configured(self) -> None:
        if not settings.github_client_id or not settings.github_client_secret:
            raise ConfigurationError(
                "GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET are required for GitHub OAuth"
            )

    async def exchange_google_code(self, code: str, redirect_uri: str) -> OAuthProfile:
        self._assert_google_configured()
        self.assert_redirect_uri_allowed(redirect_uri)

        token_payload = {
            "code": code,
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        }

        try:
            async with httpx.AsyncClient(timeout=OAUTH_HTTP_TIMEOUT) as client:
                token_response = await client.post(GOOGLE_TOKEN_URL, data=token_payload)
                if token_response.is_error:
                    raise AuthenticationError(
                        f"Google token exchange failed: {token_response.text}"
                    )
                token_data = token_response.json()
                access_token = token_data.get("access_token")
                if not access_token:
                    raise AuthenticationError("Google token exchange returned no access token")

                userinfo_response = await client.get(
                    GOOGLE_USERINFO_URL,
                    headers={"Authorization": f"Bearer {access_token}"},
                )
                if userinfo_response.is_error:
                    raise AuthenticationError(
                        f"Google userinfo request failed: {userinfo_response.text}"
                    )
                profile = userinfo_response.json()
        except AuthenticationError:
            raise
        except httpx.HTTPError as exc:
            logger.exception("Google OAuth HTTP failure")
            raise AuthenticationError(f"Google OAuth request failed: {exc}") from exc
        except Exception as exc:
            logger.exception("Unexpected Google OAuth failure")
            raise AuthenticationError(f"Google OAuth failed: {exc}") from exc

        return self._parse_google_profile(profile)

    async def exchange_github_code(self, code: str, redirect_uri: str) -> OAuthProfile:
        self._assert_github_configured()
        self.assert_redirect_uri_allowed(redirect_uri)

        token_payload = {
            "code": code,
            "client_id": settings.github_client_id,
            "client_secret": settings.github_client_secret,
            "redirect_uri": redirect_uri,
        }
        github_headers = {
            "Accept": "application/json",
        }
        api_headers = {
            "Accept": "application/vnd.github+json",
        }

        try:
            async with httpx.AsyncClient(timeout=OAUTH_HTTP_TIMEOUT) as client:
                token_response = await client.post(
                    GITHUB_TOKEN_URL,
                    data=token_payload,
                    headers=github_headers,
                )
                if token_response.is_error:
                    raise AuthenticationError(
                        f"GitHub token exchange failed: {token_response.text}"
                    )
                token_data = token_response.json()
                access_token = token_data.get("access_token")
                if not access_token:
                    error_description = token_data.get("error_description") or token_data.get(
                        "error"
                    )
                    detail = error_description or "no access token"
                    raise AuthenticationError(f"GitHub token exchange failed: {detail}")

                auth_header = {"Authorization": f"Bearer {access_token}", **api_headers}
                user_response = await client.get(GITHUB_USER_URL, headers=auth_header)
                if user_response.is_error:
                    raise AuthenticationError(
                        f"GitHub user request failed: {user_response.text}"
                    )
                profile = user_response.json()

                email = profile.get("email")
                if not email:
                    emails_response = await client.get(GITHUB_EMAILS_URL, headers=auth_header)
                    if emails_response.is_error:
                        raise AuthenticationError(
                            f"GitHub emails request failed: {emails_response.text}"
                        )
                    email = self._pick_github_verified_email(emails_response.json())
        except AuthenticationError:
            raise
        except httpx.HTTPError as exc:
            logger.exception("GitHub OAuth HTTP failure")
            raise AuthenticationError(f"GitHub OAuth request failed: {exc}") from exc
        except Exception as exc:
            logger.exception("Unexpected GitHub OAuth failure")
            raise AuthenticationError(f"GitHub OAuth failed: {exc}") from exc

        return self._parse_github_profile(profile, email)

    def _parse_google_profile(self, profile: dict) -> OAuthProfile:
        provider_user_id = profile.get("sub")
        email = profile.get("email")
        email_verified = profile.get("email_verified")
        name = profile.get("name") or email

        if not provider_user_id or not email:
            raise AuthenticationError("Google profile is missing required fields")
        if not email_verified:
            raise AuthenticationError("Google email is not verified")

        return OAuthProfile(
            provider_user_id=str(provider_user_id),
            email=str(email).lower(),
            name=str(name),
        )

    def _parse_github_profile(self, profile: dict, email: str | None) -> OAuthProfile:
        provider_user_id = profile.get("id")
        name = profile.get("name") or profile.get("login") or email

        if provider_user_id is None or not email:
            raise AuthenticationError("GitHub profile is missing a verified email")

        return OAuthProfile(
            provider_user_id=str(provider_user_id),
            email=str(email).lower(),
            name=str(name),
        )

    def _pick_github_verified_email(self, emails: list[dict]) -> str | None:
        primary_verified = next(
            (
                entry.get("email")
                for entry in emails
                if entry.get("primary") and entry.get("verified") and entry.get("email")
            ),
            None,
        )
        if primary_verified:
            return str(primary_verified)

        any_verified = next(
            (
                entry.get("email")
                for entry in emails
                if entry.get("verified") and entry.get("email")
            ),
            None,
        )
        return str(any_verified) if any_verified else None

    async def authenticate_with_oauth(
        self,
        session: AsyncSession,
        provider: OAuthProvider,
        profile: OAuthProfile,
    ) -> User:
        existing_oauth = await session.scalar(
            select(OAuthAccount).where(
                OAuthAccount.provider == provider.value,
                OAuthAccount.provider_user_id == profile.provider_user_id,
            )
        )
        if existing_oauth is not None:
            user = await session.get(User, existing_oauth.user_id)
            if user is None:
                raise AuthenticationError("Linked OAuth account has no user")
            return user

        user = await session.scalar(select(User).where(User.email == profile.email))
        if user is None:
            user = User(
                email=profile.email,
                name=profile.name,
                organization_id=None,
                super_admin=False,
                password_hash=None,
            )
            session.add(user)
            await session.flush()

        oauth_account = OAuthAccount(
            user_id=user.id,
            provider=provider.value,
            provider_user_id=profile.provider_user_id,
            email=profile.email,
        )
        session.add(oauth_account)
        try:
            await session.flush()
        except IntegrityError as exc:
            raise ConflictError("OAuth account is already linked to another user") from exc

        return user

    async def login_with_google(
        self,
        session: AsyncSession,
        code: str,
        redirect_uri: str,
    ) -> User:
        profile = await self.exchange_google_code(code, redirect_uri)
        return await self.authenticate_with_oauth(session, OAuthProvider.GOOGLE, profile)

    async def login_with_github(
        self,
        session: AsyncSession,
        code: str,
        redirect_uri: str,
    ) -> User:
        profile = await self.exchange_github_code(code, redirect_uri)
        return await self.authenticate_with_oauth(session, OAuthProvider.GITHUB, profile)


oauth_service = OAuthService()
