from __future__ import annotations

from piratehunt.agents.mock.base import FixtureDiscoveryAgent


class MockWebAgent(FixtureDiscoveryAgent):
    """Mock web/IPTV crawler backed by fixture data."""

    name = "web"
    source_platform = "web"
    fixture_name = "mock_iptv_sites.yaml"
    default_latency_range = (0.2, 0.8)
