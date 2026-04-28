from __future__ import annotations

import time
from collections.abc import AsyncIterator

import pytest
from sqlalchemy import text

from piratehunt.agents.base import DiscoveryAgent
from piratehunt.agents.mock import MockDiscordAgent, MockTelegramAgent
from piratehunt.agents.orchestrator import AgentOrchestrator
from piratehunt.agents.types import CandidateStream, DiscoveryQuery
from piratehunt.config import settings
from piratehunt.db.engine import async_session_maker, engine
from piratehunt.db.models import Base
from piratehunt.db.repository import create_match, list_candidates

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


class FailingAgent(DiscoveryAgent):
    name = "failing"

    async def _discover(self, query: DiscoveryQuery) -> AsyncIterator[CandidateStream]:
        raise RuntimeError("intentional failure")
        yield  # pragma: no cover


async def test_orchestrator_parallel_dedupe_and_failure_isolation(redis_client):
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    await redis_client.delete(settings.redis_candidates_stream)

    async with async_session_maker() as session:
        match = await create_match(session, "Discovery Demo", "https://example.com/demo.mp4")

    orchestrator = AgentOrchestrator(
        redis=redis_client,
        per_agent_budget_per_minute=10,
        global_rate_per_second=1000.0,
    )
    orchestrator.register_many(
        [
            MockTelegramAgent(latency_range=(0.2, 0.2)),
            MockDiscordAgent(latency_range=(0.2, 0.2)),
            FailingAgent(),
        ]
    )
    query = DiscoveryQuery(match_id=match.id, keywords=["ipl"])

    started = time.monotonic()
    run_id = await orchestrator.start_discovery(query)
    await orchestrator.wait_for_run(run_id)
    elapsed = time.monotonic() - started

    async with async_session_maker() as session:
        candidates = await list_candidates(session, match.id)

    assert elapsed < 1.5
    assert len(candidates) == 7
    assert orchestrator.metrics["failing"].errors == 1
    assert any(
        candidate.source_url == "https://stream.mock/shared-ipl-hd" for candidate in candidates
    )

    await orchestrator.stop()
