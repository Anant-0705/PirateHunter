from __future__ import annotations

import pytest
from PIL import Image
from redis.asyncio import Redis
from sqlalchemy import text

from piratehunt.config import settings
from piratehunt.db.engine import async_session_maker, engine
from piratehunt.db.models import Base, MatchStatus
from piratehunt.db.repository import count_fingerprints, create_match, get_match
from piratehunt.ingestion.producer import enqueue_ingestion
from piratehunt.ingestion.worker import IngestionWorker

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


async def test_worker_reads_stream_writes_db_and_emits_progress(monkeypatch):
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    redis = Redis.from_url(settings.redis_url, decode_responses=False)
    await redis.delete(settings.redis_ingest_stream, settings.redis_events_stream)

    async with async_session_maker() as session:
        match = await create_match(session, "Worker Demo", "https://example.com/demo.mp4")

    def fake_extract(_source):
        yield (b"\x00" * 44100 * 2 * 5, [Image.new("RGB", (16, 16), "red")])

    monkeypatch.setattr("piratehunt.ingestion.worker.extract_audio_and_keyframes", fake_extract)

    await enqueue_ingestion(redis, match.id, match.source_url)
    worker = IngestionWorker(redis=redis, consumer_name="test-worker")
    assert await worker.run_once(block_ms=1000)

    async with async_session_maker() as session:
        fetched = await get_match(session, match.id)
        assert fetched is not None
        assert fetched.status == MatchStatus.ready
        assert await count_fingerprints(session, match.id) == (1, 1)

    events = await redis.xrange(settings.redis_events_stream)
    assert len(events) >= 2
    await redis.aclose()
