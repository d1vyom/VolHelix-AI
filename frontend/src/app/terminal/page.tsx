"use client";

import { useState } from "react";
import { useFlowSocket } from "@/lib/flow/useFlowSocket";
import { FlowMetricsStrip } from "@/components/flow/FlowMetricsStrip";
import { FootprintChart } from "@/components/flow/FootprintChart";
import { DOMLadder } from "@/components/flow/DOMLadder";
import { TimeAndSales } from "@/components/flow/TimeAndSales";
import { LiquidityHeatmap } from "@/components/flow/LiquidityHeatmap";
import { CVDPanel } from "@/components/flow/CVDPanel";
import { VolumeProfile } from "@/components/flow/VolumeProfile";

export default function TerminalPage() {
  const [symbol, setSymbol] = useState("BTCUSDT");

  // Subscribe to all panels for now
  const { status, lastEventTs } = useFlowSocket(symbol, [
    "dom",
    "tape",
    "footprint",
    "heatmap",
    "metrics",
  ]);

  return (
    <div className="flex flex-col h-full w-full bg-[#121214] text-neutral-100 p-2 gap-2 overflow-y-auto">
      <div className="flex items-center gap-4 p-2 bg-[#1C1C1E] rounded-md shrink-0">
        <h1 className="text-xl font-bold font-mono">PRO TERMINAL</h1>
        <select
          value={symbol}
          onChange={(e) => setSymbol(e.target.value)}
          className="bg-[#2C2C2E] text-white px-3 py-1 rounded border border-[#3A3A3C] outline-none focus:border-[#007AFF]"
        >
          <option value="BTCUSDT">BTCUSDT</option>
          <option value="ETHUSDT">ETHUSDT</option>
          <option value="SOLUSDT">SOLUSDT</option>
          <option value="BNBUSDT">BNBUSDT</option>
          <option value="XRPUSDT">XRPUSDT</option>
        </select>
        <div className="text-sm text-neutral-400 font-mono">
          Socket Status: <span className={status === "LIVE" ? "text-[#34C759]" : "text-[#FF9F0A]"}>{status}</span>
        </div>
      </div>

      {/* Metrics Strip */}
      <div className="shrink-0">
        <FlowMetricsStrip symbol={symbol} />
      </div>

      <div className="flex gap-2 grow min-h-0 overflow-hidden">
        {/* Left pane: Footprint, CVD */}
        <div className="flex flex-col flex-1 gap-2 min-w-[300px]">
          <div className="flex-[2] min-h-0">
            <FootprintChart symbol={symbol} />
          </div>
          <div className="flex-[1] min-h-0">
            <CVDPanel symbol={symbol} />
          </div>
        </div>
        
        {/* Right pane: DOM, Tape, Heatmap, VP */}
        <div className="flex flex-col flex-1 gap-2 min-w-[300px]">
          <div className="flex-[2] flex gap-2 min-h-0">
            <div className="flex-1 min-w-[200px]">
              <DOMLadder symbol={symbol} />
            </div>
            <div className="flex-[0.8] min-w-[150px]">
              <TimeAndSales symbol={symbol} />
            </div>
            <div className="flex-[0.6] min-w-[100px]">
              <VolumeProfile symbol={symbol} />
            </div>
          </div>
          <div className="flex-[1] min-h-0">
            <LiquidityHeatmap symbol={symbol} />
          </div>
        </div>
      </div>
    </div>
  );
}
