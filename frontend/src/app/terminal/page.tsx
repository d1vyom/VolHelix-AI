"use client";

import { useMarket } from "@/components/MarketProvider";
import { OrderTicket } from "@/components/OrderTicket";
import { useFlowSocket } from "@/lib/flow/useFlowSocket";
import dynamic from "next/dynamic";

const WorkspaceGrid = dynamic(() => import("@/components/flow/WorkspaceGrid").then(mod => mod.WorkspaceGrid), { ssr: false });

export default function TerminalPage() {
  const {symbol,market}=useMarket();
  const {status,lastEventTs,error}=useFlowSocket(symbol,market);

  return (
    <div className="flex flex-col min-h-[calc(100vh-100px)] w-full bg-[#121214] text-neutral-100 overflow-hidden">
      {/* Terminal Header */}
      <div className="flex items-center justify-between p-2 bg-[#1C1C1E] border-b border-[#2C2C2E] shrink-0 z-10">
        <div className="flex items-center gap-4">
          <h1 className="text-lg font-extrabold font-mono text-[#f5f5f5]">
            VOLHELIX <span className="text-[#f7a600]">PRO</span>
          </h1>
          <strong>{market} · {symbol}</strong>
        </div>
        
        <div className="text-[11px] text-neutral-400 font-mono flex items-center gap-2">
          <span>{lastEventTs ? new Date(lastEventTs).toLocaleTimeString() : "Syncing..."}</span>
          <span className="w-px h-3 bg-[#2C2C2E]"></span>
          <span className="flex items-center gap-1.5">
            <div className={`w-2 h-2 rounded-full ${
              status === "LIVE" ? "bg-[#20b26c] shadow-[0_0_8px_rgba(32,178,108,0.5)]" :
              status === "WAITING" || status === "STALE" ? "bg-[#f7a600] animate-pulse" :
              "bg-[#ef454a]"
            }`} />
            {status}
          </span>
        </div>
      </div>

      {/* Workspace Area */}
      {error&&<p role="status" className="p-2 text-[#f7a600]">{error}</p>}
      <div className="min-h-[650px] h-[75vh] relative">
        <WorkspaceGrid key={`${market}:${symbol}`} symbol={symbol} />
      </div>
      <OrderTicket key={`${market}:${symbol}`} />
    </div>
  );
}
