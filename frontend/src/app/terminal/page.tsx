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
    <div className="terminal-page flex flex-col min-h-[calc(100vh-100px)] w-full bg-[#121214] text-neutral-100">
      {/* Terminal Header */}
      <div className="terminal-heading flex flex-wrap items-center justify-between gap-3 px-4 py-3 bg-[#18191f] border-b border-[#26282f] shrink-0">
        <div className="flex flex-wrap items-center gap-4">
          <h1 className="text-lg font-extrabold font-mono text-[#f5f5f5]">
            VOLHELIX <span className="text-[#f7a600]">PRO</span>
          </h1>
          <span className="text-xs text-[#b5b7c0]">Order flow workspace</span>
        </div>
        
        <div className="text-[11px] text-neutral-400 font-mono flex items-center gap-2">
          <span>{lastEventTs ? new Date(lastEventTs).toLocaleTimeString() : "No events yet"}</span>
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
      <div className="terminal-layout">
        <div className="terminal-workspace">
          <WorkspaceGrid key={`${market}:${symbol}`} symbol={symbol} />
        </div>
        <aside className="terminal-ticket"><OrderTicket key={`${market}:${symbol}`} /></aside>
      </div>
    </div>
  );
}
