import { memo, useRef, useEffect, useState, useMemo } from "react";
import { useFlowStore } from "@/lib/flow/useFlowStore";
import { PanelFrame } from "./PanelFrame";
import { TapeEntry } from "@/lib/flow/flowTypes";
import { formatTimestampIST, formatCompactNumber } from "@/lib/flow/flowFormat";
import { Filter } from "lucide-react";

const ROW_HEIGHT = 24;

const TapeRow = memo(({ entry }: { entry: TapeEntry }) => {
  const isBuy = entry.side === "BUY";
  const colorClass = isBuy ? "text-[#34C759]" : "text-[#FF453A]";
  const bgClass = entry.is_whale 
    ? (isBuy ? "bg-[#34C759]/20" : "bg-[#FF453A]/20")
    : (isBuy ? "bg-[#34C759]/5 hover:bg-[#34C759]/10" : "bg-[#FF453A]/5 hover:bg-[#FF453A]/10");
  
  return (
    <div 
      className={`flex items-center w-full px-2 py-0.5 text-xs font-mono border-b border-[#2C2C2E]/50 ${bgClass}`}
      style={{ height: ROW_HEIGHT }}
    >
      <div className="w-[80px] text-neutral-400 shrink-0">{formatTimestampIST(entry.ts)}</div>
      <div className={`flex-1 font-semibold ${colorClass}`}>{entry.price.toFixed(2)}</div>
      <div className="w-[70px] text-right text-neutral-300 shrink-0">{formatCompactNumber(entry.qty)}</div>
      <div className="w-[60px] text-right text-neutral-400 shrink-0">{formatCompactNumber(entry.quote_qty)}</div>
    </div>
  );
});
TapeRow.displayName = "TapeRow";

export function TimeAndSales({ symbol }: { symbol: string }) {
  const state = useFlowStore();
  const tape = state.tape || [];
  
  const scrollRef = useRef<HTMLDivElement>(null);
  const [scrollTop, setScrollTop] = useState(0);
  const [isPaused, setIsPaused] = useState(false);
  const [isAtTop, setIsAtTop] = useState(true);

  // We want newest at the top. The tape array has newest items at the END, so we reverse it for rendering.
  // We'll reverse it in useMemo.
  const reversedTape = useMemo(() => {
    return [...tape].reverse();
  }, [tape]);

  // Handle scroll to implement virtualized rendering and "pause on scroll"
  const handleScroll = (e: React.UIEvent<HTMLDivElement>) => {
    const target = e.currentTarget;
    setScrollTop(target.scrollTop);
    
    // If we scrolled down away from the top (0), we pause auto-scrolling
    if (target.scrollTop > 5) {
      setIsPaused(true);
      setIsAtTop(false);
    } else {
      setIsPaused(false);
      setIsAtTop(true);
    }
  };

  // Virtualization calculations
  const containerHeight = scrollRef.current?.clientHeight || 400;
  const totalHeight = reversedTape.length * ROW_HEIGHT;
  
  // Find visible indices with a small overscan buffer (e.g., 5 items)
  const startIndex = Math.max(0, Math.floor(scrollTop / ROW_HEIGHT) - 5);
  const endIndex = Math.min(
    reversedTape.length - 1,
    Math.ceil((scrollTop + containerHeight) / ROW_HEIGHT) + 5
  );

  const visibleItems = reversedTape.slice(startIndex, endIndex + 1);
  const offsetY = startIndex * ROW_HEIGHT;

  const handleResume = () => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = 0;
      setIsPaused(false);
      setIsAtTop(true);
    }
  };

  return (
    <PanelFrame title="Time & Sales" symbol={symbol} health={state.health}>
      {/* Header columns */}
      <div className="flex items-center w-full px-2 py-1 text-[10px] font-mono text-neutral-500 uppercase tracking-wider bg-[#2C2C2E] shrink-0 border-b border-[#3A3A3C]">
        <div className="w-[80px] shrink-0">Time</div>
        <div className="flex-1">Price</div>
        <div className="w-[70px] text-right shrink-0">Size</div>
        <div className="w-[60px] text-right shrink-0">USD</div>
      </div>

      {/* Virtualized List Container */}
      <div 
        ref={scrollRef}
        className="flex-1 overflow-y-auto no-scrollbar relative"
        onScroll={handleScroll}
        onMouseEnter={() => setIsPaused(true)}
        onMouseLeave={() => { if (isAtTop) setIsPaused(false); }}
      >
        {reversedTape.length === 0 ? (
          <div className="flex items-center justify-center h-full text-sm text-neutral-500 font-mono">
            Waiting for trades...
          </div>
        ) : (
          <div style={{ height: totalHeight, position: "relative" }}>
            <div style={{ transform: `translateY(${offsetY}px)`, position: "absolute", top: 0, left: 0, right: 0 }}>
              {visibleItems.map((entry, idx) => (
                <TapeRow key={`${entry.ts}-${entry.price}-${entry.qty}-${idx}`} entry={entry} />
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Pause/Resume Pill */}
      {isPaused && !isAtTop && (
        <div className="absolute bottom-10 left-1/2 -translate-x-1/2 z-10">
          <button 
            onClick={handleResume}
            className="flex items-center gap-1 px-3 py-1 bg-[#007AFF] hover:bg-[#0056b3] text-white text-xs rounded-full font-semibold shadow-lg transition-colors"
          >
            Resume feed
          </button>
        </div>
      )}

      {/* Footer Strip */}
      <div className="h-6 bg-[#2C2C2E] shrink-0 border-t border-[#3A3A3C] flex items-center px-2 text-[10px] font-mono text-neutral-400 gap-4">
        <div>RATE: {state.metrics?.trade_rate?.toFixed(1) || 0}/s</div>
        <div>VOL/S: {formatCompactNumber(state.metrics?.volume_rate || 0)}</div>
        <div className="flex-1 flex justify-end items-center gap-2">
          <span>1M B/S</span>
          <div className="w-16 h-1.5 bg-[#3A3A3C] rounded-full overflow-hidden flex">
            <div 
              className="bg-[#34C759] h-full" 
              style={{ width: `${Math.min(100, Math.max(0, (state.metrics?.buy_sell_ratio || 1) / 2 * 100))}%` }} 
            />
            <div className="bg-[#FF453A] flex-1" />
          </div>
        </div>
      </div>
    </PanelFrame>
  );
}
