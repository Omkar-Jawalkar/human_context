import uuid
from unittest.mock import AsyncMock, patch

import pytest

from app.core.exceptions import RateLimitError, ServiceUnavailableError
from app.services.rate_limit_service import RateLimitService, rate_limit_service


@pytest.fixture
def service() -> RateLimitService:
    return RateLimitService()


@pytest.mark.asyncio
async def test_assert_chat_send_allowed_allows_under_limit(service):
    user_id = uuid.uuid4()
    mock_redis = AsyncMock()
    mock_redis.eval = AsyncMock(return_value=1)

    with patch("app.services.rate_limit_service.get_redis", return_value=mock_redis):
        await service.assert_chat_send_allowed(user_id)

    mock_redis.eval.assert_awaited_once()
    key = mock_redis.eval.await_args.args[2]
    assert str(user_id) in key


@pytest.mark.asyncio
async def test_assert_chat_send_allowed_rejects_over_limit(service):
    user_id = uuid.uuid4()
    mock_redis = AsyncMock()
    mock_redis.eval = AsyncMock(return_value=0)
    mock_redis.ttl = AsyncMock(return_value=3600)

    with patch("app.services.rate_limit_service.get_redis", return_value=mock_redis):
        with pytest.raises(RateLimitError) as exc_info:
            await service.assert_chat_send_allowed(user_id)

    assert exc_info.value.code == "rate_limit_error"
    assert exc_info.value.retry_after_seconds == 3600
    mock_redis.ttl.assert_awaited_once()


@pytest.mark.asyncio
async def test_assert_chat_send_allowed_redis_error_fails_closed(service):
    user_id = uuid.uuid4()
    mock_redis = AsyncMock()
    mock_redis.eval = AsyncMock(side_effect=ConnectionError("redis down"))

    with patch("app.services.rate_limit_service.get_redis", return_value=mock_redis):
        with pytest.raises(ServiceUnavailableError, match="Rate limit service unavailable"):
            await service.assert_chat_send_allowed(user_id)


@pytest.mark.asyncio
async def test_assert_chat_send_allowed_uses_fallback_ttl_when_missing(service):
    user_id = uuid.uuid4()
    mock_redis = AsyncMock()
    mock_redis.eval = AsyncMock(return_value=0)
    mock_redis.ttl = AsyncMock(return_value=-1)

    with (
        patch("app.services.rate_limit_service.get_redis", return_value=mock_redis),
        patch("app.services.rate_limit_service.settings") as mock_settings,
    ):
        mock_settings.chat_send_rate_limit = 20
        mock_settings.chat_send_rate_limit_window_seconds = 21600
        with pytest.raises(RateLimitError) as exc_info:
            await service.assert_chat_send_allowed(user_id)

    assert exc_info.value.retry_after_seconds == 21600


def test_rate_limit_service_singleton():
    assert rate_limit_service is not None
