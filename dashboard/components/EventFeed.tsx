"use client";

import { useEffect, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { DashboardEvent } from "@/lib/types";

interface EventFeedProps {
  events: DashboardEvent[];
}

export default function EventFeed({ events }: EventFeedProps) {
  const feedRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to top when new events arrive
  useEffect(() => {
    if (feedRef.current) {
      feedRef.current.scrollTo({ top: 0, behavior: "smooth" });
    }
  }, [events]);

  const getEventColor = (type: string) => {
    switch (type) {
      case "candidate_discovered":
        return "text-blue-400";
      case "pirate_confirmed":
        return "text-rose-500";
      case "takedown_drafted":
        return "text-amber-400";
      case "takedown_status_changed":
        return "text-emerald-400";
      case "ingestion_started":
        return "text-cyan-400";
      default:
        return "text-slate-400";
    }
  };

  const getEventIcon = (type: string) => {
    switch (type) {
      case "candidate_discovered":
        return "📡";
      case "pirate_confirmed":
        return "🚨";
      case "takedown_drafted":
        return "📝";
      case "takedown_status_changed":
        return "✅";
      case "ingestion_started":
        return "⚡";
      default:
        return "•";
    }
  };

  const formatEventType = (type: string) => {
    return type
      .replace(/_/g, " ")
      .split(" ")
      .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
      .join(" ");
  };

  return (
    <div className="relative h-full flex flex-col">
      <div className="absolute top-0 left-0 right-0 h-8 bg-gradient-to-b from-slate-900 to-transparent z-10 pointer-events-none" />
      
      <div
        ref={feedRef}
        className="overflow-y-auto h-full space-y-3 p-2 scrollbar-hide"
      >
        <AnimatePresence initial={false}>
          {events.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full text-slate-600 animate-pulse">
              <span className="text-2xl mb-2">🔭</span>
              <span className="text-sm font-medium">Scanning for threats...</span>
            </div>
          ) : (
            events.map((event, idx) => (
              <motion.div
                key={`${event.type}-${idx}`}
                initial={{ x: -20, opacity: 0 }}
                animate={{ x: 0, opacity: 1 }}
                exit={{ x: 20, opacity: 0 }}
                transition={{ type: "spring", stiffness: 300, damping: 30 }}
                className="group relative bg-slate-800/40 hover:bg-slate-800/80 border border-slate-700/50 p-3 rounded-lg transition-colors cursor-default"
              >
                <div className="flex items-start gap-3">
                  <div className="flex-shrink-0 w-8 h-8 rounded-full bg-slate-900 flex items-center justify-center text-sm shadow-inner group-hover:scale-110 transition-transform">
                    {getEventIcon(event.type)}
                  </div>
                  
                  <div className="flex-1 min-w-0">
                    <div className="flex justify-between items-start mb-1">
                      <span className={`text-xs font-bold uppercase tracking-wider ${getEventColor(event.type)}`}>
                        {formatEventType(event.type)}
                      </span>
                      <span className="text-[10px] text-slate-500 font-mono">
                        {new Date().toLocaleTimeString([], { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                      </span>
                    </div>
                    
                    <div className="text-sm text-slate-300 line-clamp-1">
                      {event.platform && <span className="font-semibold text-slate-100">{event.platform}</span>}
                      {event.url && <span className="opacity-60 ml-1">• {new URL(event.url).hostname}</span>}
                    </div>
                  </div>
                </div>
                
                {idx === 0 && (
                  <motion.div 
                    layoutId="pulse"
                    className="absolute -left-1 top-1/2 -translate-y-1/2 w-1 h-6 bg-cyan-500 rounded-full shadow-[0_0_8px_rgba(6,182,212,0.6)]"
                  />
                )}
              </motion.div>
            ))
          )}
        </AnimatePresence>
      </div>
      
      <div className="absolute bottom-0 left-0 right-0 h-8 bg-gradient-to-t from-slate-900 to-transparent z-10 pointer-events-none" />
    </div>
  );
}
