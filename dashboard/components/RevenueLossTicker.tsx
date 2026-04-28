"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";

interface RevenueLossTickerProps {
  value: number;
}

export default function RevenueLossTicker({ value }: RevenueLossTickerProps) {
  const [displayValue, setDisplayValue] = useState(0);

  useEffect(() => {
    // Animate the value counter
    const increment = value / 100;
    let current = displayValue;

    const timer = setInterval(() => {
      current += increment;
      if (current >= value) {
        setDisplayValue(value);
        clearInterval(timer);
      } else {
        setDisplayValue(current);
      }
    }, 30);

    return () => clearInterval(timer);
  }, [value, displayValue]);

  const formatValue = (v: number) => {
    if (v >= 1000000) return `${(v / 1000000).toFixed(1)}M`;
    if (v >= 1000) return `${(v / 1000).toFixed(1)}K`;
    return Math.round(v).toString();
  };

  return (
    <div className="text-center">
      <motion.div
        className="text-4xl font-bold text-red-500"
        initial={{ scale: 0.8 }}
        animate={{ scale: 1 }}
        transition={{ duration: 0.3 }}
      >
        ₹{formatValue(displayValue)}
      </motion.div>
      <p className="text-xs text-slate-500 mt-1">Est. Loss (INR)</p>
    </div>
  );
}
