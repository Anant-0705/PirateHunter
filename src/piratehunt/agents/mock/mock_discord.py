from __future__ import annotations

from piratehunt.agents.mock.base import FixtureDiscoveryAgent


class MockDiscordAgent(FixtureDiscoveryAgent):
    """Mock Discord crawler backed by fixture data."""

    name = "discord"
    source_platform = "discord"
    fixture_name = "mock_discord_servers.yaml"
    default_latency_range = (0.5, 2.0)
