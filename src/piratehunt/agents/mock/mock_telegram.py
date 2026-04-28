from __future__ import annotations

from piratehunt.agents.mock.base import FixtureDiscoveryAgent


class MockTelegramAgent(FixtureDiscoveryAgent):
    """Mock Telegram crawler backed by fixture data."""

    name = "telegram"
    source_platform = "telegram"
    fixture_name = "mock_telegram_channels.yaml"
    default_latency_range = (0.5, 2.0)
