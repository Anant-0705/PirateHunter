"use client";

import React from "react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from "recharts";

interface TakedownFunnelProps {
  detected: number;
  verified: number;
  drafted: number;
  submitted: number;
  taken_down: number;
}

export default function TakedownFunnel({
  detected,
  verified,
  drafted,
  submitted,
  taken_down,
}: TakedownFunnelProps) {
  const data = [
    { stage: "Detected", value: detected, color: "#94a3b8" },
    { stage: "Verified", value: verified, color: "#38bdf8" },
    { stage: "Drafted", value: drafted, color: "#fbbf24" },
    { stage: "Submitted", value: submitted, color: "#f59e0b" },
    { stage: "Resolved", value: taken_down, color: "#10b981" },
  ];

  const CustomTooltip = ({ active, payload }: any) => {
    if (active && payload && payload.length) {
      return (
        <div className="bg-slate-900/90 backdrop-blur-md border border-slate-700 p-3 rounded-lg shadow-2xl">
          <p className="text-xs font-bold text-slate-400 uppercase tracking-widest mb-1">{payload[0].payload.stage}</p>
          <p className="text-xl font-black text-white">{payload[0].value}</p>
          <p className="text-[10px] text-slate-500 mt-1">
            {((payload[0].value / (detected || 1)) * 100).toFixed(1)}% of discovery
          </p>
        </div>
      );
    }
    return null;
  };

  return (
    <div className="w-full h-full pt-2">
      <ResponsiveContainer width="100%" height={180}>
        <BarChart
          data={data}
          margin={{ top: 5, right: 5, left: -20, bottom: 5 }}
        >
          <CartesianGrid vertical={false} strokeDasharray="3 3" stroke="#334155" />
          <XAxis
            dataKey="stage"
            tick={{ fontSize: 10, fill: "#64748b", fontWeight: 600 }}
            axisLine={false}
            tickLine={false}
            height={30}
          />
          <YAxis 
            tick={{ fontSize: 10, fill: "#64748b" }}
            axisLine={false}
            tickLine={false}
          />
          <Tooltip content={<CustomTooltip />} cursor={{ fill: '#1e293b', opacity: 0.4 }} />
          <Bar
            dataKey="value"
            radius={[4, 4, 0, 0]}
            animationDuration={1500}
            animationEasing="ease-out"
          >
            {data.map((entry, index) => (
              <Cell key={`cell-${index}`} fill={entry.color} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
