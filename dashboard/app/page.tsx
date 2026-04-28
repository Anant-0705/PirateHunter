"use client";

import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useDashboardStore } from "@/lib/store";
import { connectWebSocket, disconnectWebSocket } from "@/lib/ws";
import { getDashboardSummary, getActivePirates, getTakedownFunnel } from "@/lib/api";
import Globe from "@/components/Globe";
import EventFeed from "@/components/EventFeed";
import TakedownFunnel from "@/components/TakedownFunnel";
import RevenueLossTicker from "@/components/RevenueLossTicker";

export default function DashboardPage() {
  const store = useDashboardStore();
  const [matchId, setMatchId] = useState<string>("");
  const [isLoading, setIsLoading] = useState(false);

  // Initialize dashboard
  useEffect(() => {
    const defaultMatch = "00000000-0000-0000-0000-000000000001";
    setMatchId(defaultMatch);
    useDashboardStore.getState().setMatchId(defaultMatch);
  }, []);

  // Load initial data and connect WebSocket
  useEffect(() => {
    if (!matchId) return;

    const loadData = async () => {
      try {
        setIsLoading(true);

        // Load initial data
        const [summary, pirates, funnel] = await Promise.all([
          getDashboardSummary(matchId),
          getActivePirates(matchId),
          getTakedownFunnel(matchId),
        ]);

        useDashboardStore.getState().setSummary({
          active_pirates: summary.active_pirates,
          total_detected: summary.total_detected,
          total_drafted: summary.total_drafted,
          total_submitted: summary.total_submitted,
          total_taken_down: summary.total_taken_down,
          est_revenue_loss_inr: summary.est_revenue_loss_inr,
          avg_detection_latency_ms: summary.avg_detection_latency_ms,
        });

        useDashboardStore.getState().setPirates(pirates);

        // Connect WebSocket for live updates
        await connectWebSocket([matchId]);
      } catch (error) {
        console.error("Failed to load dashboard:", error);
      } finally {
        setIsLoading(false);
      }
    };

    loadData();

    return () => {
      disconnectWebSocket();
    };
  }, [matchId]);

  return (
    <div className="bg-[#020617] text-slate-100 min-h-screen font-sans selection:bg-cyan-500/30">
      {/* Dynamic Background Noise */}
      <div className="fixed inset-0 pointer-events-none opacity-[0.03] z-[100] bg-[url('https://grainy-gradients.vercel.app/noise.svg')]" />
      
      {/* Header */}
      <header className="border-b border-slate-800/60 bg-slate-950/50 backdrop-blur-xl sticky top-0 z-50 px-6 py-4">
        <div className="max-w-[1800px] mx-auto flex items-center justify-between">
          <div className="flex items-center gap-4">
            <div className="relative">
              <div className="w-10 h-10 bg-cyan-500 rounded-lg flex items-center justify-center shadow-[0_0_20px_rgba(6,182,212,0.4)]">
                <span className="text-2xl font-black text-slate-950">P</span>
              </div>
              <div className="absolute -bottom-1 -right-1 w-4 h-4 bg-slate-950 rounded-full flex items-center justify-center">
                <div className={`w-2 h-2 rounded-full ${store.isConnected ? "bg-green-500 shadow-[0_0_8px_#22c55e]" : "bg-red-500 shadow-[0_0_8px_#ef4444]"}`} />
              </div>
            </div>
            <div>
              <h1 className="text-xl font-bold tracking-tight bg-gradient-to-r from-white to-slate-400 bg-clip-text text-transparent">PirateHunt <span className="text-cyan-500">v2.0</span></h1>
              <div className="flex items-center gap-2 mt-0.5">
                <span className="text-[10px] font-mono text-slate-500 uppercase tracking-widest">Global Surveillance Ops</span>
                <div className="w-1 h-1 rounded-full bg-slate-700" />
                <span className="text-[10px] font-mono text-slate-500">ID: {matchId.slice(0, 8)}...</span>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-6">
            <div className="flex flex-col items-end">
              <div className="flex items-center gap-2">
                <div className="w-2 h-2 rounded-full bg-cyan-500 animate-ping" />
                <span className="text-xs font-bold text-cyan-400 uppercase tracking-tighter">Live Stream</span>
              </div>
              <span className="text-[10px] font-mono text-slate-500 uppercase tracking-widest">Real-time Event Bridge</span>
            </div>
            
            <div className="h-8 w-px bg-slate-800" />
            
            <button className="bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-bold py-2 px-4 rounded-md border border-slate-700 transition-all active:scale-95">
              Force Scan
            </button>
          </div>
        </div>
      </header>

      <main className="max-w-[1800px] mx-auto p-6">
        <AnimatePresence mode="wait">
          {isLoading ? (
            <motion.div 
              key="loading"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="flex flex-col items-center justify-center py-40"
            >
              <div className="relative w-24 h-24">
                <div className="absolute inset-0 border-4 border-cyan-500/20 rounded-full" />
                <div className="absolute inset-0 border-4 border-t-cyan-500 rounded-full animate-spin" />
                <div className="absolute inset-0 flex items-center justify-center">
                  <span className="text-xs font-black text-cyan-500 animate-pulse">BOOT</span>
                </div>
              </div>
              <p className="text-slate-500 text-sm font-medium mt-8 tracking-widest uppercase animate-pulse">Syncing Global Datastream...</p>
            </motion.div>
          ) : (
            <motion.div 
              key="content"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              className="grid grid-cols-12 gap-6"
            >
              {/* Left Side: Globe (8 Columns) */}
              <div className="col-span-12 lg:col-span-8 space-y-6">
                <div className="relative aspect-[16/9] lg:h-[650px] bg-slate-950 rounded-2xl border border-slate-800 shadow-2xl overflow-hidden group">
                  <div className="absolute inset-0 bg-gradient-to-b from-cyan-500/[0.02] to-transparent pointer-events-none" />
                  <Globe pirates={store.activePirates} />
                  
                  {/* Decorative Overlays */}
                  <div className="absolute inset-0 pointer-events-none border-[20px] border-slate-950/20" />
                  <div className="absolute top-4 right-4 z-10 flex gap-2">
                    <div className="bg-slate-900/80 backdrop-blur px-2 py-1 rounded border border-slate-700 text-[10px] font-mono text-cyan-500">2048x1280</div>
                    <div className="bg-slate-900/80 backdrop-blur px-2 py-1 rounded border border-slate-700 text-[10px] font-mono text-cyan-500">60FPS</div>
                  </div>
                </div>

                {/* Bottom Stats Grid */}
                <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4">
                  {[
                    { label: "Detected", val: store.totalDetected, color: "text-cyan-400" },
                    { label: "Active", val: store.activeCount, color: "text-rose-500" },
                    { label: "Verified", val: store.totalDetected, color: "text-blue-400" },
                    { label: "Drafted", val: store.totalDrafted, color: "text-amber-400" },
                    { label: "Submitted", val: store.totalSubmitted, color: "text-orange-500" },
                    { label: "Resolved", val: store.totalTakenDown, color: "text-emerald-400" },
                  ].map((stat, i) => (
                    <motion.div 
                      key={stat.label}
                      initial={{ opacity: 0, y: 20 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ delay: i * 0.1 }}
                      className="bg-slate-900/50 border border-slate-800 p-4 rounded-xl hover:bg-slate-800/50 transition-colors group cursor-default"
                    >
                      <div className="text-[10px] font-mono text-slate-500 uppercase tracking-widest mb-1 group-hover:text-slate-300 transition-colors">{stat.label}</div>
                      <div className={`text-2xl font-black ${stat.color} tabular-nums tracking-tighter`}>{stat.val}</div>
                    </motion.div>
                  ))}
                </div>
              </div>

              {/* Right Side: Feed & Funnel (4 Columns) */}
              <div className="col-span-12 lg:col-span-4 flex flex-col gap-6">
                {/* Revenue Loss Card */}
                <div className="bg-gradient-to-br from-slate-900 to-slate-950 border border-slate-800 rounded-2xl p-6 shadow-xl relative overflow-hidden group">
                  <div className="absolute -right-4 -top-4 w-24 h-24 bg-rose-500/10 blur-3xl group-hover:bg-rose-500/20 transition-all" />
                  <div className="relative z-10">
                    <div className="flex items-center justify-between mb-4">
                      <div className="text-xs font-bold text-slate-400 uppercase tracking-widest">Impact Assessment</div>
                      <div className="w-8 h-8 rounded-lg bg-rose-500/10 flex items-center justify-center text-rose-500">📉</div>
                    </div>
                    <RevenueLossTicker value={store.revenueeLoss} />
                    <div className="mt-4 pt-4 border-t border-slate-800 flex justify-between items-center">
                      <span className="text-[10px] text-slate-500 font-mono uppercase tracking-widest">Matches Baseline</span>
                      <span className="text-[10px] text-rose-500 font-bold">+12.4% vs last hr</span>
                    </div>
                  </div>
                </div>

                {/* Event Feed */}
                <div className="flex-1 bg-slate-900/50 border border-slate-800 rounded-2xl p-6 shadow-xl flex flex-col overflow-hidden min-h-[300px]">
                  <div className="flex items-center justify-between mb-4">
                    <div className="text-xs font-bold text-slate-400 uppercase tracking-widest">Global Event Stream</div>
                    <div className="flex items-center gap-1.5">
                      <div className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                      <span className="text-[10px] font-mono text-emerald-500 uppercase">Synced</span>
                    </div>
                  </div>
                  <div className="flex-1 overflow-hidden">
                    <EventFeed events={store.events} />
                  </div>
                </div>

                {/* Takedown Funnel */}
                <div className="bg-slate-900/50 border border-slate-800 rounded-2xl p-6 shadow-xl relative overflow-hidden group">
                  <div className="flex items-center justify-between mb-4">
                    <div className="text-xs font-bold text-slate-400 uppercase tracking-widest">Conversion Funnel</div>
                    <span className="text-[10px] font-mono text-slate-500">LIVE LATENCY: {Math.round(store.avgLatencyMs)}ms</span>
                  </div>
                  <TakedownFunnel
                    detected={store.totalDetected}
                    verified={store.totalDetected}
                    drafted={store.totalDrafted}
                    submitted={store.totalSubmitted}
                    taken_down={store.totalTakenDown}
                  />
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </main>

      <footer className="max-w-[1800px] mx-auto px-6 py-8 flex flex-col md:flex-row items-center justify-between gap-4 border-t border-slate-800 mt-12 mb-8">
        <div className="text-[10px] font-mono text-slate-500 uppercase tracking-widest">© 2026 PirateHunt Advanced Agentic Intelligence • Confidential Ops</div>
        <div className="flex items-center gap-4 text-[10px] font-mono text-slate-500">
          <span className="hover:text-cyan-500 transition-colors cursor-pointer">Security Protocol v4</span>
          <span className="w-1 h-1 rounded-full bg-slate-700" />
          <span className="hover:text-cyan-500 transition-colors cursor-pointer">API Documentation</span>
          <span className="w-1 h-1 rounded-full bg-slate-700" />
          <span className="hover:text-cyan-500 transition-colors cursor-pointer">System Logs</span>
        </div>
      </footer>
    </div>
  );
}
