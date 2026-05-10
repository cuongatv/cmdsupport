"""
Simple Redis-based rate limiter for CMD Support endpoints.
"""

import time

from fastapi import HTTPException
from redis.asyncio import Redis

from app.config import settings


async def _get_redis() -> Redis:
    """Create a Redis connection from app settings."""
    return Redis(
        host=settings.redis_host,
        port=settings.redis_port,
        password=settings.redis_password or None,
        db=settings.redis_db,
        decode_responses=True,
    )


async def check_rate_limit(
    user_id: str,
    key_prefix: str = "rl:advice",
    max_requests: int = 10,
    window_seconds: int = 60,
) -> None:
    """
    Check rate limit for a user. Raises HTTP 429 if exceeded.

    Uses a sliding-window counter bucketed by minute.
    """
    minute_bucket = int(time.time()) // window_seconds
    key = f"{key_prefix}:{user_id}:{minute_bucket}"

    redis = await _get_redis()
    try:
        count = await redis.incr(key)
        if count == 1:
            await redis.expire(key, window_seconds + 5)

        if count > max_requests:
            raise HTTPException(
                status_code=429,
                detail="Vượt giới hạn tần suất tư vấn. Vui lòng thử lại sau 1 phút.",
            )
    finally:
        await redis.aclose()
