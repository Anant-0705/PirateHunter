"""Redis stream consumer that bridges backend events to WebSocket clients."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from typing import Optional

import redis.asyncio as redis

from piratehunt.api.realtime.geolocation import lookup_location
from piratehunt.api.realtime.manager import WebSocketConnectionManager
from piratehunt.api.realtime.types import (
    CandidateDiscovered,
    CleanConfirmed,
    DashboardEvent,
    IngestionCompleted,
    IngestionStarted,
    PirateConfirmed,
    TakedownDrafted,
    TakedownStatusChanged,
    VerificationStarted,
)
from piratehunt.config import settings

logger = logging.getLogger(__name__)

# Global connection manager (singleton)
_connection_manager: Optional[WebSocketConnectionManager] = None


def get_connection_manager() -> WebSocketConnectionManager:
    """Get or create the global connection manager."""
    global _connection_manager
    if _connection_manager is None:
        _connection_manager = WebSocketConnectionManager()
    return _connection_manager


async def normalize_event(stream_name: str, event_data: dict) -> Optional[DashboardEvent]:
    """
    Convert a raw Redis stream event into a DashboardEvent.
    
    Args:
        stream_name: Name of the Redis stream (e.g., "piratehunt:events")
        event_data: Parsed event data from Redis
        
    Returns:
        DashboardEvent if parseable, None otherwise.
    """
    try:
        event_type = event_data.get("event_type") or event_data.get("type")
        
        # Ingestion events (from piratehunt:events stream)
        if event_type == "ingestion_started":
            return IngestionStarted(
                match_id=event_data.get("match_id"),
                match_name=event_data.get("match_name", "Unknown"),
            )
        elif event_type == "ingestion_completed":
            return IngestionCompleted(match_id=event_data.get("match_id"))
        
        # Candidate/discovery events (from piratehunt:candidates stream)
        elif event_type == "candidate_discovered":
            url = event_data.get("source_url", "")
            location = lookup_location(url)
            return CandidateDiscovered(
                match_id=event_data.get("match_id"),
                candidate_id=event_data.get("candidate_id"),
                platform=event_data.get("source_platform", "unknown"),
                url=url,
                location=location,
                confidence_hint=event_data.get("confidence_hint", 0.5),
            )
        
        # Verification events (from piratehunt:verifications stream)
        elif event_type == "verification_started":
            return VerificationStarted(
                match_id=event_data.get("match_id"),
                candidate_id=event_data.get("candidate_id"),
            )
        elif event_type == "pirate_confirmed":
            url = event_data.get("source_url", "")
            location = lookup_location(url)
            discovered_at = event_data.get("discovered_at")
            if isinstance(discovered_at, str):
                discovered_at = datetime.fromisoformat(discovered_at)
            verified_at = datetime.utcnow()
            latency_ms = (verified_at - discovered_at).total_seconds() * 1000 if discovered_at else 0
            
            return PirateConfirmed(
                match_id=event_data.get("match_id"),
                candidate_id=event_data.get("candidate_id"),
                verification_result_id=event_data.get("verification_result_id"),
                platform=event_data.get("source_platform", "unknown"),
                url=url,
                location=location,
                audio_score=event_data.get("audio_score", 0),
                visual_score=event_data.get("visual_score", 0),
                combined_score=event_data.get("combined_score", 0),
                gemini_verdict=event_data.get("gemini_detected_sport", "Unknown"),
                detection_latency_ms=latency_ms,
            )
        elif event_type == "clean_confirmed":
            return CleanConfirmed(
                match_id=event_data.get("match_id"),
                candidate_id=event_data.get("candidate_id"),
            )
        
        # Takedown events (from piratehunt:takedowns stream)
        elif event_type == "takedown_drafted":
            return TakedownDrafted(
                match_id=event_data.get("match_id"),
                case_id=event_data.get("case_id"),
                platform=event_data.get("platform", "unknown"),
                gemini_polish_applied=event_data.get("gemini_polish_applied", False),
            )
        elif event_type == "takedown_status_changed":
            return TakedownStatusChanged(
                match_id=event_data.get("match_id"),
                case_id=event_data.get("case_id"),
                from_status=event_data.get("from_status", "unknown"),
                to_status=event_data.get("to_status", "unknown"),
            )
        else:
            logger.warning(f"Unknown event type: {event_type}")
            return None
            
    except Exception as e:
        logger.error(f"Failed to normalize event {event_data}: {e}")
        return None


async def run_event_bridge(redis_client: redis.Redis) -> None:
    """
    Main event bridge loop: consume from Redis streams and broadcast to WebSocket clients.
    
    Args:
        redis_client: Redis async client.
    """
    manager = get_connection_manager()
    
    # Stream names and their consumer groups
    streams = {
        "piratehunt:events": "dashboard:events",
        "piratehunt:candidates": "dashboard:events",
        "piratehunt:verifications": "dashboard:events",
        "piratehunt:takedowns": "dashboard:events",
    }
    
    # Create consumer groups if they don't exist
    for stream_name, group_name in streams.items():
        try:
            await redis_client.xgroup_create(stream_name, group_name, id="0", mkstream=True)
        except redis.ResponseError as e:
            if "BUSYGROUP" not in str(e):
                logger.warning(f"Failed to create group {group_name}: {e}")
    
    logger.info("Event bridge started, consuming from 4 streams...")
    
    consumer_name = "dashboard-bridge"
    last_ids = {stream: ">" for stream in streams.keys()}
    
    while True:
        try:
            # Read from all streams
            messages = await redis_client.xreadgroup(
                groupname="dashboard:events",
                consumername=consumer_name,
                streams={
                    "piratehunt:events": last_ids.get("piratehunt:events", ">"),
                    "piratehunt:candidates": last_ids.get("piratehunt:candidates", ">"),
                    "piratehunt:verifications": last_ids.get("piratehunt:verifications", ">"),
                    "piratehunt:takedowns": last_ids.get("piratehunt:takedowns", ">"),
                },
                block=1000,
                count=10,
            )
            
            if not messages:
                continue
            
            for stream_name, stream_messages in messages:
                stream_name_str = stream_name.decode() if isinstance(stream_name, bytes) else stream_name
                
                for msg_id, msg_data in stream_messages:
                    try:
                        # Parse message
                        event_dict = {}
                        for key, value in msg_data.items():
                            k = key.decode() if isinstance(key, bytes) else key
                            v = value.decode() if isinstance(value, bytes) else value
                            try:
                                event_dict[k] = json.loads(v)
                            except (json.JSONDecodeError, TypeError):
                                event_dict[k] = v
                        
                        # Unwrap "data" field if present
                        if "data" in event_dict:
                            event_dict = json.loads(event_dict["data"]) if isinstance(event_dict["data"], str) else event_dict["data"]
                        
                        # Normalize to DashboardEvent
                        event = await normalize_event(stream_name_str, event_dict)
                        
                        if event:
                            # Broadcast to all subscribed clients
                            await manager.broadcast(event)
                            logger.debug(f"Broadcasted event: {event.type}")
                        
                        # Acknowledge message
                        await redis_client.xack(stream_name_str, "dashboard:events", msg_id)
                        last_ids[stream_name_str] = msg_id
                        
                    except Exception as e:
                        logger.error(f"Error processing message from {stream_name_str}: {e}")
        
        except asyncio.CancelledError:
            logger.info("Event bridge shutting down...")
            break
        except Exception as e:
            logger.error(f"Event bridge error: {e}")
            await asyncio.sleep(5)


async def start_event_bridge() -> asyncio.Task:
    """Start the event bridge as a background task.
    
    Returns:
        The asyncio Task running the bridge.
    """
    redis_client = await redis.from_url(settings.redis_url)
    task = asyncio.create_task(run_event_bridge(redis_client))
    logger.info("Event bridge task created")
    return task
