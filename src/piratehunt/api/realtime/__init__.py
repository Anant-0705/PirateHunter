"""Real-time dashboard infrastructure."""

from __future__ import annotations

from piratehunt.api.realtime.manager import WebSocketConnectionManager
from piratehunt.api.realtime.types import DashboardEvent

__all__ = [
    "WebSocketConnectionManager",
    "DashboardEvent",
]
