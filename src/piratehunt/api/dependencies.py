from __future__ import annotations

from collections.abc import AsyncIterator

from redis.asyncio import Redis

from piratehunt.config import settings
from piratehunt.db.engine import get_session

__all__ = ["get_redis", "get_session", "get_db"]

# Alias for backward compatibility with router conventions
get_db = get_session


async def get_redis() -> AsyncIterator[Redis]:
    """Yield a Redis client for request-scoped FastAPI dependencies."""
    redis = Redis.from_url(settings.redis_url, decode_responses=False)
    try:
        yield redis
    finally:
        await redis.aclose()
