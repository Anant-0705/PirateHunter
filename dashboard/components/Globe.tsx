"use client";

import { useEffect, useRef, useState, useMemo } from "react";
import dynamic from "next/dynamic";
import { PirateEntry } from "@/lib/types";

// Import Globe dynamically to avoid SSR issues with Three.js
const GlobeGL = dynamic(() => import("react-globe.gl"), {
  ssr: false,
  loading: () => (
    <div className="flex items-center justify-center h-full w-full bg-slate-900 rounded-lg">
      <div className="animate-pulse text-cyan-500 font-medium">Initializing 3D Core...</div>
    </div>
  ),
});

interface GlobeProps {
  pirates: PirateEntry[];
}

export default function Globe({ pirates }: GlobeProps) {
  const globeRef = useRef<any>();
  const [dimensions, setDimensions] = useState({ width: 0, height: 0 });
  const containerRef = useRef<HTMLDivElement>(null);

  // Resize handler
  useEffect(() => {
    if (containerRef.current) {
      const { clientWidth, clientHeight } = containerRef.current;
      setDimensions({ width: clientWidth, height: clientHeight });
    }

    const handleResize = () => {
      if (containerRef.current) {
        const { clientWidth, clientHeight } = containerRef.current;
        setDimensions({ width: clientWidth, height: clientHeight });
      }
    };

    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  // Format data for globe
  const globeData = useMemo(() => {
    return pirates.map((p) => ({
      id: p.candidate_id,
      lat: p.location.lat,
      lng: p.location.lng,
      size: p.status === "active" ? 0.5 : 0.3,
      color: p.status === "active" ? "#ef4444" : p.status === "draft" ? "#eab308" : "#10b981",
      label: `${p.platform}: ${new URL(p.url).hostname}`,
      status: p.status,
    }));
  }, [pirates]);

  // Arcs to show connections (e.g. from a central monitoring station in Mumbai)
  const arcData = useMemo(() => {
    const center = { lat: 19.076, lng: 72.877 }; // Mumbai
    return pirates.map((p) => ({
      startLat: center.lat,
      startLng: center.lng,
      endLat: p.location.lat,
      endLng: p.location.lng,
      color: p.status === "active" ? ["#06b6d4", "#ef4444"] : ["#06b6d4", "#10b981"],
    }));
  }, [pirates]);

  useEffect(() => {
    if (globeRef.current) {
      globeRef.current.controls().autoRotate = true;
      globeRef.current.controls().autoRotateSpeed = 0.5;
    }
  }, [globeRef.current]);

  return (
    <div ref={containerRef} className="w-full h-full relative overflow-hidden group">
      <div className="absolute top-4 left-4 z-10 flex flex-col gap-2 pointer-events-none">
        <div className="bg-slate-900/80 backdrop-blur-md border border-slate-700 p-3 rounded-lg shadow-xl">
          <div className="text-xs font-bold text-slate-400 uppercase tracking-widest mb-2">Live Nodes</div>
          <div className="flex flex-col gap-1">
            <div className="flex items-center gap-2">
              <div className="w-2 h-2 rounded-full bg-red-500 animate-pulse" />
              <span className="text-sm text-slate-200">Active Pirate: {pirates.filter(p => p.status === "active").length}</span>
            </div>
            <div className="flex items-center gap-2">
              <div className="w-2 h-2 rounded-full bg-yellow-500" />
              <span className="text-sm text-slate-200">In Queue: {pirates.filter(p => p.status === "draft").length}</span>
            </div>
            <div className="flex items-center gap-2">
              <div className="w-2 h-2 rounded-full bg-emerald-500" />
              <span className="text-sm text-slate-200">Resolved: {pirates.filter(p => p.status === "submitted").length}</span>
            </div>
          </div>
        </div>
      </div>

      <GlobeGL
        ref={globeRef}
        width={dimensions.width}
        height={dimensions.height}
        backgroundColor="rgba(0,0,0,0)"
        globeImageUrl="//unpkg.com/three-globe/example/img/earth-night.jpg"
        bumpImageUrl="//unpkg.com/three-globe/example/img/earth-topology.png"
        pointsData={globeData}
        pointLat="lat"
        pointLng="lng"
        pointColor="color"
        pointRadius="size"
        pointsMerge={true}
        pointAltitude={0.1}
        arcsData={arcData}
        arcColor="color"
        arcDashLength={0.4}
        arcDashGap={4}
        arcDashAnimateTime={2000}
        arcStroke={0.5}
        labelsData={globeData}
        labelLat="lat"
        labelLng="lng"
        labelText="label"
        labelSize={0.5}
        labelColor={() => "rgba(255, 255, 255, 0.7)"}
        labelDotRadius={0.3}
        labelAltitude={0.15}
      />

      <div className="absolute bottom-4 right-4 z-10 pointer-events-none opacity-0 group-hover:opacity-100 transition-opacity">
        <div className="text-[10px] text-slate-500 font-mono">DRAG TO ROTATE • SCROLL TO ZOOM</div>
      </div>
    </div>
  );
}
