// TypeScript types for PirateHunt Dashboard

export interface GeoLocation {
  lat: number;
  lng: number;
  country: string;
  country_name: string;
  city?: string;
}

export interface DashboardEvent {
  type: string;
  timestamp: string;
  match_id?: string;
  candidate_id?: string;
  platform?: string;
  url?: string;
  location?: GeoLocation;
  [key: string]: any;
}

export interface PirateEntry {
  candidate_id: string;
  platform: string;
  url: string;
  confidence: number;
  location: GeoLocation;
  discovered_at: string;
  last_seen: string;
  status: "active" | "draft" | "submitted";
}

export interface DashboardSummary {
  match_id: string;
  active_pirates: number;
  total_detected: number;
  total_drafted: number;
  total_submitted: number;
  total_taken_down: number;
  est_revenue_loss_inr: number;
  avg_detection_latency_ms: number;
  top_platforms: Array<{ platform: string; count: number }>;
}

export interface TakedownFunnelData {
  detected: number;
  verified: number;
  drafted: number;
  submitted: number;
  taken_down: number;
}

export interface TimelineEvent {
  timestamp: string;
  detections: number;
  takedowns: number;
}
