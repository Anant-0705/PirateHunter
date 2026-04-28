// WebSocket client for real-time event streaming
import { useDashboardStore } from "./store";
import { DashboardEvent } from "./types";

let socket: WebSocket | null = null;
let reconnectAttempts = 0;
const MAX_RECONNECT_ATTEMPTS = 10;
const RECONNECT_DELAY = 2000;
let reconnectTimeout: NodeJS.Timeout | null = null;

const WS_URL = process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8000/ws";

export async function connectWebSocket(matchIds: string[]): Promise<void> {
  if (socket && socket.readyState === WebSocket.OPEN) {
    console.log("WebSocket already connected");
    return;
  }

  console.log("Connecting to WebSocket:", WS_URL);

  try {
    socket = new WebSocket(WS_URL);

    socket.onopen = () => {
      console.log("✅ WebSocket connected");
      useDashboardStore.getState().setConnected(true);
      reconnectAttempts = 0;

      // Subscribe to match events
      if (matchIds.length > 0 && socket) {
        socket.send(
          JSON.stringify({
            action: "subscribe",
            match_ids: matchIds,
          })
        );
        console.log("Subscribed to matches:", matchIds);
      }
    };

    socket.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        
        // Handle heartbeat
        if (data.type === "heartbeat") {
          return;
        }

        // Handle dashboard events
        console.log("📡 Received event:", data.type);
        handleEvent(data as DashboardEvent);
      } catch (error) {
        console.error("Error parsing WebSocket message:", error);
      }
    };

    socket.onclose = (event) => {
      console.log("❌ WebSocket disconnected:", event.code, event.reason);
      useDashboardStore.getState().setConnected(false);
      socket = null;

      // Attempt reconnection
      if (reconnectAttempts < MAX_RECONNECT_ATTEMPTS) {
        reconnectAttempts++;
        console.log(
          `Reconnecting... (attempt ${reconnectAttempts}/${MAX_RECONNECT_ATTEMPTS})`
        );
        reconnectTimeout = setTimeout(() => {
          connectWebSocket(matchIds);
        }, RECONNECT_DELAY);
      } else {
        console.error("Max reconnection attempts reached");
      }
    };

    socket.onerror = (error) => {
      console.error("WebSocket error:", error);
      useDashboardStore.getState().setConnected(false);
    };
  } catch (error) {
    console.error("Failed to create WebSocket:", error);
    useDashboardStore.getState().setConnected(false);
  }
}

export function disconnectWebSocket(): void {
  if (reconnectTimeout) {
    clearTimeout(reconnectTimeout);
    reconnectTimeout = null;
  }

  if (socket) {
    console.log("Disconnecting WebSocket");
    socket.close();
    socket = null;
    useDashboardStore.getState().setConnected(false);
  }
}

function handleEvent(event: DashboardEvent): void {
  const store = useDashboardStore.getState();

  // Add to event feed
  store.addEvent(event);

  // Update statistics based on event type
  switch (event.type) {
    case "candidate_discovered":
      // Don't increment detected here, wait for verification
      break;

    case "pirate_confirmed":
      store.incrementDetected();
      // Add to pirates list if location available
      if (event.location) {
        store.addPirate({
          candidate_id: event.candidate_id || "",
          platform: event.platform || "unknown",
          url: event.url || "",
          confidence: event.combined_score || 0,
          location: event.location,
          discovered_at: event.timestamp,
          last_seen: event.timestamp,
          status: "active",
        });
      }
      break;

    case "takedown_drafted":
      store.incrementDrafted();
      break;

    case "takedown_status_changed":
      if (event.to_status === "submitted") {
        store.incrementSubmitted();
      } else if (event.to_status === "taken_down") {
        store.incrementTakenDown();
      }
      break;
  }
}

export function isConnected(): boolean {
  return socket?.readyState === WebSocket.OPEN || false;
}
