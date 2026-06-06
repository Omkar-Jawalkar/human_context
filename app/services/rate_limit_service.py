from __future__ import annotations

import logging
import uuid

from app.core.config import settings
from app.core.exceptions import AppError, RateLimitError, ServiceUnavailableError
from app.core.redis import get_redis

logger = logging.getLogger(__name__)

_CHAT_SEND_KEY_PREFIX = "hc:rate_limit:chat_send:user:"

_CONSUME_SLOT_LUA = """
local current = redis.call('INCR', KEYS[1])
if current == 1 then
  redis.call('EXPIRE', KEYS[1], ARGV[1])
end
if current > tonumber(ARGV[2]) then
  redis.call('DECR', KEYS[1])
  return 0
end
return current
"""


class RateLimitService:
    def _chat_send_key(self, user_id: uuid.UUID) -> str:
        return f"{_CHAT_SEND_KEY_PREFIX}{user_id}"

    async def assert_chat_send_allowed(self, user_id: uuid.UUID) -> None:
        key = self._chat_send_key(user_id)
        limit = settings.chat_send_rate_limit
        window_seconds = settings.chat_send_rate_limit_window_seconds

        try:
            redis = get_redis()
            allowed = await redis.eval(
                _CONSUME_SLOT_LUA,
                1,
                key,
                window_seconds,
                limit,
            )
        except AppError:
            raise
        except Exception as exc:
            logger.exception("Rate limit check failed for user %s", user_id)
            raise ServiceUnavailableError("Rate limit service unavailable") from exc

        if allowed:
            return

        try:
            retry_after_seconds = await redis.ttl(key)
        except Exception as exc:
            logger.exception("Rate limit TTL lookup failed for user %s", user_id)
            raise ServiceUnavailableError("Rate limit service unavailable") from exc

        if retry_after_seconds < 0:
            retry_after_seconds = window_seconds

        raise RateLimitError(
            f"Chat message limit reached ({limit} per {window_seconds // 3600} hours).",
            retry_after_seconds=retry_after_seconds,
        )


rate_limit_service = RateLimitService()
