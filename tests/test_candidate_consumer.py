from __future__ import annotations

import pytest
from sqlalchemy import text

from piratehunt.agents.candidate_consumer import CandidateConsumer
from piratehunt.agents.types import CandidateStream
from piratehunt.config import settings
from piratehunt.db.engine import async_session_maker, engine
from piratehunt.db.models import Base, CandidateStatus
from piratehunt.db.repository import (
    create_match,
    get_candidate_by_source_url,
    insert_candidate_stream,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


async def test_candidate_consumer_marks_candidate_queued(redis_client):
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    await redis_client.delete(settings.redis_candidates_stream)

    async with async_session_maker() as session:
        match = await create_match(session, "Consumer Demo", "https://example.com/demo.mp4")
        candidate = CandidateStream(
            match_id=match.id,
            source_platform="web",
            source_url="https://free-sports-mirror.mock/ipl-live",
            discovered_by_agent="web",
            metadata={"is_pirate": True},
            confidence_hint=0.58,
        )
        inserted = await insert_candidate_stream(session, candidate)
        assert inserted is not None

    await redis_client.xadd(
        settings.redis_candidates_stream, {"event": candidate.model_dump_json()}
    )
    consumer = CandidateConsumer(redis=redis_client, consumer_name="test-candidate-consumer")
    assert await consumer.run_once(block_ms=1000)

    async with async_session_maker() as session:
        updated = await get_candidate_by_source_url(session, match.id, candidate.source_url)

    assert updated is not None
    assert updated.status == CandidateStatus.queued_for_verification
