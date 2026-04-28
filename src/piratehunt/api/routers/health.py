from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from piratehunt.api.dependencies import get_redis, get_session
from piratehunt.config import logger
from piratehunt.db.repository import latest_successful_verification_time

router = APIRouter(tags=["health"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]
RedisDep = Annotated[Redis, Depends(get_redis)]


@router.get("/health")
async def health_check(
    session: SessionDep,
    redis: RedisDep,
) -> dict[str, object]:
    """Health check endpoint including Postgres and Redis connectivity."""
    postgres_status = "ok"
    redis_status = "ok"

    try:
        await session.execute(text("SELECT 1"))
    except Exception as exc:
        logger.warning("Postgres health check failed: %s", exc)
        postgres_status = "unavailable"

    try:
        await redis.ping()
    except Exception as exc:
        logger.warning("Redis health check failed: %s", exc)
        redis_status = "unavailable"

    status = "ok" if postgres_status == "ok" and redis_status == "ok" else "degraded"
    latest_verification = None
    if postgres_status == "ok":
        latest = await latest_successful_verification_time(session)
        latest_verification = latest.isoformat() if latest else None
    return {
        "status": status,
        "phase": 4,
        "postgres": postgres_status,
        "redis": redis_status,
        "verification_worker": {"last_successful_verification_at": latest_verification},
    }
