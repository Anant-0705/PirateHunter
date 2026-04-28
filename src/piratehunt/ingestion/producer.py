from __future__ import annotations

import json
from uuid import UUID

from redis.asyncio import Redis

from piratehunt.config import settings
from piratehunt.ingestion.events import IngestionRequested


async def enqueue_ingestion(
    redis: Redis,
    match_id: UUID,
    source_url: str,
    *,
    stream: str | None = None,
) -> str:
    """Enqueue a match ingestion request on the Redis stream."""
    event = IngestionRequested(match_id=match_id, source_url=source_url)
    event_id = await redis.xadd(
        stream or settings.redis_ingest_stream,
        {"event": event.model_dump_json()},
    )
    if isinstance(event_id, bytes):
        return event_id.decode("utf-8")
    return str(event_id)


def decode_stream_event(fields: dict[bytes | str, bytes | str]) -> IngestionRequested:
    """Decode an ingestion request from Redis stream fields."""
    raw = fields.get(b"event") or fields.get("event")
    if raw is None:
        raw = json.dumps(
            {
                key.decode() if isinstance(key, bytes) else key: value
                for key, value in fields.items()
            }
        )
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    return IngestionRequested.model_validate_json(raw)
