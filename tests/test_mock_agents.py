from __future__ import annotations

from uuid import uuid4

import pytest

from piratehunt.agents.mock import (
    MockDiscordAgent,
    MockRedditAgent,
    MockTelegramAgent,
    MockWebAgent,
)
from piratehunt.agents.types import CandidateStream, DiscoveryQuery


async def _collect(agent, query: DiscoveryQuery) -> list[CandidateStream]:
    return [candidate async for candidate in agent.discover(query)]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("agent_cls", "expected_count"),
    [
        (MockTelegramAgent, 4),
        (MockDiscordAgent, 4),
        (MockRedditAgent, 4),
        (MockWebAgent, 3),
    ],
)
async def test_mock_agents_yield_expected_fixture_candidates(agent_cls, expected_count):
    agent = agent_cls(latency_range=(0.0, 0.0))
    query = DiscoveryQuery(match_id=uuid4(), keywords=["ipl"], languages=["en", "hi", "bn"])

    candidates = await _collect(agent, query)

    assert len(candidates) == expected_count
    assert all(candidate.source_platform == agent.source_platform for candidate in candidates)
    assert all(0.0 <= candidate.confidence_hint <= 1.0 for candidate in candidates)


@pytest.mark.asyncio
async def test_mock_agents_respect_keyword_filtering():
    agent = MockTelegramAgent(latency_range=(0.0, 0.0))
    query = DiscoveryQuery(match_id=uuid4(), keywords=["archive"])

    candidates = await _collect(agent, query)

    assert len(candidates) == 1
    assert candidates[0].source_url == "https://t.me/mock_asia_cup_archive"


@pytest.mark.asyncio
async def test_mock_agents_handle_empty_queries():
    agent = MockWebAgent(latency_range=(0.0, 0.0))
    query = DiscoveryQuery(match_id=uuid4(), keywords=[])

    assert await _collect(agent, query) == []


@pytest.mark.asyncio
async def test_mock_agent_health_check_returns_sane_values():
    agent = MockRedditAgent(latency_range=(0.0, 0.0))

    health = await agent.health_check()

    assert health.healthy is True
    assert health.error is None
    assert health.last_run is not None
