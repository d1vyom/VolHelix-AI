"use client";

import { useState } from "react";
import { useFlowSocket } from "@/lib/flow/useFlowSocket";
import { WorkspaceGrid } from "@/components/flow/WorkspaceGrid";

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
    <div className="flex flex-col h-full w-full bg-[#121214] text-neutral-100 overflow-hidden">
      {/* Terminal Header */}
      <div className="flex items-center justify-between p-2 bg-[#1C1C1E] border-b border-[#2C2C2E] shrink-0 z-10">
        <div className="flex items-center gap-4">
          <h1 className="text-lg font-extrabold font-mono text-[#f5f5f5]">
            VOLHELIX <span className="text-[#f7a600]">PRO</span>
          </h1>
          <select
            value={symbol}
            onChange={(e) => setSymbol(e.target.value)}
            className="bg-[#121214] text-[#f5f5f5] px-3 py-1 rounded border border-[#2C2C2E] outline-none focus:border-[#f7a600] text-sm font-bold tracking-wider uppercase cursor-pointer"
          >
            <option value="BTCUSDT">BTCUSDT</option>
            <option value="ETHUSDT">ETHUSDT</option>
            <option value="SOLUSDT">SOLUSDT</option>
            <option value="BNBUSDT">BNBUSDT</option>
            <option value="XRPUSDT">XRPUSDT</option>
          </select>
        </div>
        
        <div className="text-[11px] text-neutral-400 font-mono flex items-center gap-2">
          <span>{lastEventTs ? new Date(lastEventTs).toLocaleTimeString() : "Syncing..."}</span>
          <span className="w-px h-3 bg-[#2C2C2E]"></span>
          <span className="flex items-center gap-1.5">
            <div className={`w-2 h-2 rounded-full ${
              status === "LIVE" ? "bg-[#20b26c] shadow-[0_0_8px_rgba(32,178,108,0.5)]" :
              status === "CONNECTING" || status === "RECONNECTING" ? "bg-[#f7a600] animate-pulse" :
              "bg-[#ef454a]"
            }`} />
            {status}
          </span>
        </div>
      </div>

      {/* Workspace Area */}
      <div className="flex-1 min-h-0 relative">
        <WorkspaceGrid symbol={symbol} />
      </div>
    </div>
  );
}
