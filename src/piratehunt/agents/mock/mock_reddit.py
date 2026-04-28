from __future__ import annotations

from piratehunt.agents.mock.base import FixtureDiscoveryAgent


class MockRedditAgent(FixtureDiscoveryAgent):
    """Mock Reddit crawler backed by fixture data."""

    name = "reddit"
    source_platform = "reddit"
    fixture_name = "mock_reddit_posts.yaml"
    default_latency_range = (1.0, 3.0)
