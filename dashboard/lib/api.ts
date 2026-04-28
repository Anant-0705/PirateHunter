// API client for dashboard aggregation endpoints
import {
  DashboardSummary,
  PirateEntry,
  TakedownFunnelData,
  TimelineEvent,
} from "./types";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function fetchAPI<T>(endpoint: string): Promise<T> {
  const response = await fetch(`${API_URL}${endpoint}`);
  if (!response.ok) {
    throw new Error(`API error: ${response.statusText}`);
  }
  return response.json();
}

export async function getDashboardSummary(
  matchId: string
): Promise<DashboardSummary> {
  return fetchAPI<DashboardSummary>(`/dashboard/summary?match_id=${matchId}`);
}

export async function getActivePirates(
  matchId: string
): Promise<PirateEntry[]> {
  return fetchAPI<PirateEntry[]>(`/dashboard/pirates/active?match_id=${matchId}`);
}

export async function getTakedownFunnel(
  matchId: string
): Promise<TakedownFunnelData> {
  return fetchAPI<TakedownFunnelData>(`/dashboard/funnel?match_id=${matchId}`);
}

export async function getTimeline(
  matchId: string,
  window: number = 60
): Promise<TimelineEvent[]> {
  return fetchAPI<TimelineEvent[]>(
    `/dashboard/timeline?match_id=${matchId}&window=${window}`
  );
}

export async function healthCheck(): Promise<{ status: string }> {
  return fetchAPI<{ status: string }>("/health");
}
