// Zustand store for dashboard state management
import { create } from "zustand";
import { DashboardEvent, PirateEntry } from "./types";

interface DashboardState {
  // Connection state
  isConnected: boolean;
  setConnected: (connected: boolean) => void;

  // Match state
  matchId: string | null;
  setMatchId: (id: string) => void;

  // Events
  events: DashboardEvent[];
  addEvent: (event: DashboardEvent) => void;
  clearEvents: () => void;

  // Pirates
  activePirates: PirateEntry[];
  setPirates: (pirates: PirateEntry[]) => void;
  addPirate: (pirate: PirateEntry) => void;

  // Statistics
  activeCount: number;
  totalDetected: number;
  totalDrafted: number;
  totalSubmitted: number;
  totalTakenDown: number;
  revenueeLoss: number;
  avgLatencyMs: number;

  setSummary: (summary: {
    active_pirates: number;
    total_detected: number;
    total_drafted: number;
    total_submitted: number;
    total_taken_down: number;
    est_revenue_loss_inr: number;
    avg_detection_latency_ms: number;
  }) => void;

  incrementDetected: () => void;
  incrementDrafted: () => void;
  incrementSubmitted: () => void;
  incrementTakenDown: () => void;
}

export const useDashboardStore = create<DashboardState>((set) => ({
  // Connection
  isConnected: false,
  setConnected: (connected) => set({ isConnected: connected }),

  // Match
  matchId: null,
  setMatchId: (id) => set({ matchId: id }),

  // Events (keep last 50)
  events: [],
  addEvent: (event) =>
    set((state) => ({
      events: [event, ...state.events].slice(0, 50),
    })),
  clearEvents: () => set({ events: [] }),

  // Pirates
  activePirates: [],
  setPirates: (pirates) => set({ activePirates: pirates }),
  addPirate: (pirate) =>
    set((state) => ({
      activePirates: [pirate, ...state.activePirates],
    })),

  // Statistics
  activeCount: 0,
  totalDetected: 0,
  totalDrafted: 0,
  totalSubmitted: 0,
  totalTakenDown: 0,
  revenueeLoss: 0,
  avgLatencyMs: 0,

  setSummary: (summary) =>
    set({
      activeCount: summary.active_pirates,
      totalDetected: summary.total_detected,
      totalDrafted: summary.total_drafted,
      totalSubmitted: summary.total_submitted,
      totalTakenDown: summary.total_taken_down,
      revenueeLoss: summary.est_revenue_loss_inr,
      avgLatencyMs: summary.avg_detection_latency_ms,
    }),

  incrementDetected: () =>
    set((state) => ({
      totalDetected: state.totalDetected + 1,
      activeCount: state.activeCount + 1,
    })),
  incrementDrafted: () =>
    set((state) => ({ totalDrafted: state.totalDrafted + 1 })),
  incrementSubmitted: () =>
    set((state) => ({
      totalSubmitted: state.totalSubmitted + 1,
      activeCount: Math.max(0, state.activeCount - 1),
    })),
  incrementTakenDown: () =>
    set((state) => ({ totalTakenDown: state.totalTakenDown + 1 })),
}));
