"""WebSocket endpoint for real-time dashboard events."""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from piratehunt.api.realtime.bridge import get_connection_manager, start_event_bridge
from piratehunt.api.realtime.manager import WebSocketConnectionManager

logger = logging.getLogger(__name__)

router = APIRouter(tags=["realtime"])

# Global reference to the bridge task
_bridge_task: Optional[asyncio.Task] = None


async def ensure_bridge_running() -> None:
    """Ensure the event bridge task is running."""
    global _bridge_task
    if _bridge_task is None or _bridge_task.done():
        _bridge_task = await start_event_bridge()


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """
    WebSocket endpoint for real-time dashboard updates.
    
    Client sends: {"action": "subscribe", "match_ids": ["match-uuid-1", "match-uuid-2"]}
    Server sends: DashboardEvent objects with all necessary rendering data
    
    Special messages:
    - {"type": "heartbeat"}: Server ping to keep connection alive
    """
    await ensure_bridge_running()
    
    manager = get_connection_manager()
    
    try:
        client_id = await manager.connect(websocket)
        logger.info(f"WebSocket client {client_id} connected")
        
        # Start heartbeat task
        heartbeat_task = asyncio.create_task(_heartbeat_loop(websocket, manager))
        
        # Wait for initial subscription
        try:
            message = await asyncio.wait_for(websocket.receive_json(), timeout=10.0)
        except asyncio.TimeoutError:
            logger.warning(f"Client {client_id} didn't subscribe within 10s, closing")
            await websocket.close(code=4000, reason="Subscription timeout")
            heartbeat_task.cancel()
            await manager.disconnect(websocket)
            return
        
        action = message.get("action")
        match_ids = message.get("match_ids", [])
        
        if action == "subscribe":
            await manager.subscribe(websocket, match_ids)
            logger.info(f"Client {client_id} subscribed to {len(match_ids)} matches")
            
            # Replay history for subscribed matches
            if match_ids:
                await manager.replay_history(websocket, match_ids)
            
            # Now stream live events
            while True:
                try:
                    message = await websocket.receive_json()
                    
                    # Handle subscription changes
                    if message.get("action") == "subscribe":
                        match_ids = message.get("match_ids", [])
                        await manager.subscribe(websocket, match_ids)
                        logger.debug(f"Client {client_id} re-subscribed to {len(match_ids)} matches")
                    
                except WebSocketDisconnect:
                    break
                except Exception as e:
                    logger.error(f"Error handling WebSocket message: {e}")
                    break
        
        else:
            logger.warning(f"Client {client_id} didn't send subscribe action: {action}")
            await websocket.close(code=4001, reason="Invalid action")
    
    except WebSocketDisconnect:
        logger.info(f"Client disconnected before initialization")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        await manager.disconnect(websocket)
        try:
            await websocket.close()
        except Exception:
            pass


async def _heartbeat_loop(
    websocket: WebSocket, manager: WebSocketConnectionManager
) -> None:
    """Periodically send heartbeat pings to keep connection alive."""
    while True:
        try:
            await asyncio.sleep(manager.heartbeat_interval)
            await manager.send_heartbeat(websocket)
        except Exception:
            break
