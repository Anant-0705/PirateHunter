"""WebSocket connection manager for dashboard clients."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Optional

from fastapi import WebSocket
from pydantic import ValidationError

from piratehunt.api.realtime.types import DashboardEvent

logger = logging.getLogger(__name__)


class WebSocketConnectionManager:
    """Manages WebSocket connections with optional per-match filtering."""

    def __init__(self, heartbeat_interval: int = 30):
        """Initialize the connection manager.
        
        Args:
            heartbeat_interval: Seconds between heartbeat pings (keep-alive).
        """
        self.heartbeat_interval = heartbeat_interval
        # Map from WebSocket to (client_id, match_ids set)
        self.active_connections: dict[WebSocket, tuple[str, set[str]]] = {}
        # Recent events per match (last N)
        self.event_history: dict[str, list[DashboardEvent]] = {}
        self.max_history = 50
        self.lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket) -> str:
        """Accept and register a WebSocket connection.
        
        Args:
            websocket: The FastAPI WebSocket object.
            
        Returns:
            client_id: Unique identifier for this connection.
        """
        await websocket.accept()
        client_id = f"client_{id(websocket)}"
        async with self.lock:
            self.active_connections[websocket] = (client_id, set())
        logger.info(f"Client {client_id} connected. Total: {len(self.active_connections)}")
        return client_id

    async def disconnect(self, websocket: WebSocket) -> None:
        """Unregister a WebSocket connection."""
        async with self.lock:
            if websocket in self.active_connections:
                client_id, _ = self.active_connections.pop(websocket)
                logger.info(f"Client {client_id} disconnected. Total: {len(self.active_connections)}")

    async def subscribe(self, websocket: WebSocket, match_ids: list[str]) -> None:
        """Subscribe a client to specific matches.
        
        Args:
            websocket: The client connection.
            match_ids: List of match UUIDs to subscribe to.
        """
        async with self.lock:
            if websocket in self.active_connections:
                client_id, _ = self.active_connections[websocket]
                self.active_connections[websocket] = (client_id, set(match_ids))
                logger.info(f"Client {client_id} subscribed to {len(match_ids)} matches")

    def _matches_subscription(self, websocket: WebSocket, event: DashboardEvent) -> bool:
        """Check if a client is subscribed to this event's match."""
        if websocket not in self.active_connections:
            return False
        _, match_ids = self.active_connections[websocket]
        # If no filters, send to all
        if not match_ids:
            return True
        # Otherwise check if event's match_id is in subscriptions
        event_dict = event.model_dump()
        match_id = event_dict.get("match_id")
        return match_id in match_ids if match_id else False

    async def broadcast(self, event: DashboardEvent) -> None:
        """Broadcast an event to subscribed clients.
        
        Args:
            event: The DashboardEvent to send.
        """
        # Store in history
        event_dict = event.model_dump()
        match_id = event_dict.get("match_id")
        
        if match_id:
            async with self.lock:
                if match_id not in self.event_history:
                    self.event_history[match_id] = []
                self.event_history[match_id].append(event)
                # Keep only last N events
                if len(self.event_history[match_id]) > self.max_history:
                    self.event_history[match_id] = self.event_history[match_id][-self.max_history :]

        # Send to clients
        disconnected = []
        async with self.lock:
            # Make a copy of connections to avoid holding lock during sends
            clients_to_send = list(self.active_connections.keys())
        
        for client in clients_to_send:
            try:
                if self._matches_subscription(client, event):
                    await client.send_json(event_dict)
            except Exception as e:
                logger.warning(f"Failed to send event to client: {e}")
                disconnected.append(client)
        
        # Remove dead connections
        for client in disconnected:
            await self.disconnect(client)

    async def send_personal_message(
        self, websocket: WebSocket, message: str | dict
    ) -> None:
        """Send a message to a specific client.
        
        Args:
            websocket: The client connection.
            message: String or dict to send.
        """
        try:
            if isinstance(message, dict):
                await websocket.send_json(message)
            else:
                await websocket.send_text(message)
        except Exception as e:
            logger.warning(f"Failed to send personal message: {e}")
            await self.disconnect(websocket)

    async def replay_history(self, websocket: WebSocket, match_ids: list[str]) -> None:
        """Replay recent event history to a newly connected client.
        
        Args:
            websocket: The client connection.
            match_ids: Matches to replay history for.
        """
        events_to_send = []
        async with self.lock:
            for match_id in match_ids:
                if match_id in self.event_history:
                    events_to_send.extend(self.event_history[match_id])
        
        # Send in order (oldest first)
        events_to_send.sort(key=lambda e: e.timestamp)
        for event in events_to_send:
            try:
                await websocket.send_json(event.model_dump())
            except Exception as e:
                logger.warning(f"Failed to send replay event: {e}")
                break

    async def send_heartbeat(self, websocket: WebSocket) -> None:
        """Send a keepalive ping to a client.
        
        Args:
            websocket: The client connection.
        """
        try:
            await websocket.send_json({"type": "heartbeat", "timestamp": "2026-01-01T00:00:00Z"})
        except Exception as e:
            logger.warning(f"Heartbeat failed: {e}")
            await self.disconnect(websocket)
