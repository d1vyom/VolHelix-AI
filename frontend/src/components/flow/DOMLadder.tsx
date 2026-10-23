import { useRef, useEffect, useState, useMemo, memo } from "react";
import { useFlowStore } from "@/lib/flow/useFlowStore";
import { PanelFrame } from "./PanelFrame";
import { LadderLevel } from "@/lib/flow/flowTypes";
import { formatCompactNumber, formatPrice } from "@/lib/flow/flowFormat";
import { Crosshair } from "lucide-react";
import { useMarket } from "../MarketProvider";

const ROW_HEIGHT = 20;

const LadderRow = memo(({ 
  level, 
  isBestBid, 
  isBestAsk,
  onStage
}: { 
  level: LadderLevel; 
  isBestBid: boolean; 
  isBestAsk: boolean;
  onStage: (price:number)=>void;
}) => {
  // Use depth_pct for background bar width
  const depthWidth = `${Math.min(100, (level.depth_pct || 0) * 100)}%`;
  
  const isBid = level.bid_size > 0;
  const isAsk = level.ask_size > 0;
  
  const bgClass = isBestBid ? "bg-[#34C759]/20" : isBestAsk ? "bg-[#FF453A]/20" : "hover:bg-[#2C2C2E]";
  const priceColor = isBid ? "text-[#34C759]" : isAsk ? "text-[#FF453A]" : "text-neutral-300";

  return (
    <button type="button" aria-label={`Stage limit at ${level.price}`} onClick={()=>onStage(level.price)}
      className={`dom-row items-center w-full text-xs font-mono border-b border-[#2C2C2E]/30 relative cursor-pointer ${bgClass}`}
      style={{ height: ROW_HEIGHT }}
    >
      {/* Background depth bar (Ask side - Red) */}
      {isAsk && (
        <div 
          className="absolute top-0 bottom-0 right-[50%] bg-[#FF453A]/10 pointer-events-none" 
          style={{ width: depthWidth }}
        />
      )}
      
      {/* Background depth bar (Bid side - Green) */}
      {isBid && (
        <div 
          className="absolute top-0 bottom-0 left-[50%] bg-[#34C759]/10 pointer-events-none" 
          style={{ width: depthWidth }}
        />
      )}

      {/* Columns */}

      
      <div className="min-w-0 text-right pr-2 text-neutral-300 relative z-10">
        {level.bid_size > 0 ? formatCompactNumber(level.bid_size) : ""}
        {level.is_wall && isBid && <div className="absolute left-1 top-1/2 -translate-y-1/2 w-1.5 h-1.5 rounded-full bg-[#34C759] shadow-[0_0_4px_#34C759]" title="Bid Wall" />}
      </div>
      
      <div className={`flex-1 text-center font-bold relative z-10 ${priceColor}`}>
        {formatPrice(level.price)}
      </div>
      
      <div className="min-w-0 text-left pl-2 text-neutral-300 relative z-10">
        {level.ask_size > 0 ? formatCompactNumber(level.ask_size) : ""}
        {level.is_wall && isAsk && <div className="absolute right-1 top-1/2 -translate-y-1/2 w-1.5 h-1.5 rounded-full bg-[#FF453A] shadow-[0_0_4px_#FF453A]" title="Ask Wall" />}
      </div>
      

      
      {/* Traded Volume column */}
      <div className="min-w-0 flex items-center justify-end px-1 text-[10px] text-neutral-400 gap-1 relative z-10">
        {level.traded_sell > 0 && <span className="text-[#FF453A]">{formatCompactNumber(level.traded_sell)}</span>}
        {(level.traded_buy > 0 || level.traded_sell > 0) && <span className="text-neutral-600">|</span>}
        {level.traded_buy > 0 && <span className="text-[#34C759]">{formatCompactNumber(level.traded_buy)}</span>}
      </div>
    </button>
  );
});
LadderRow.displayName = "LadderRow";

export function DOMLadder({ symbol }: { symbol: string }) {
  const state = useFlowStore();
  const {market}=useMarket();
  const stage=(price:number)=>window.dispatchEvent(new CustomEvent('volhelix:stage-order',{detail:{market,symbol,price}}));
  const dom = state.dom;
  
  const scrollRef = useRef<HTMLDivElement>(null);
  const [autoCenter, setAutoCenter] = useState(true);

  // Determine levels and reverse for rendering (highest price at top)
  const sortedLevels = useMemo(() => {
    if (!dom?.levels) return [];
    return [...dom.levels].sort((a, b) => b.price - a.price);
  }, [dom]);

  // Handle centering
  useEffect(() => {
    if (!autoCenter || !scrollRef.current || sortedLevels.length === 0 || !dom) return;
    
    // Find index of mid price
    const midIndex = sortedLevels.findIndex(l => l.price <= dom.mid);
    if (midIndex >= 0) {
      const containerHeight = scrollRef.current.clientHeight;
      const targetScroll = (midIndex * ROW_HEIGHT) - (containerHeight / 2) + (ROW_HEIGHT / 2);
      scrollRef.current.scrollTop = targetScroll;
    }
  }, [dom, dom?.mid, sortedLevels, autoCenter]);

  return (
    <PanelFrame title="DOM Ladder" symbol={symbol} health={state.health}>
      <div className="flex flex-col h-full w-full bg-[#121214]">
        
        {/* Header/Controls */}
        <div className="flex items-center px-2 py-1 text-[10px] font-mono text-neutral-400 bg-[#2C2C2E] border-b border-[#3A3A3C] shrink-0 justify-between">
          <div className="flex items-center gap-3">
            <span>SPREAD: {dom?.spread_bps?.toFixed(1) ?? '—'} bps</span>
            <span>IMB: {dom ? (dom.book_imbalance * 100).toFixed(0) : '—'}%</span>
          </div>
          <button 
            onClick={() => setAutoCenter(!autoCenter)}
            className={`p-1 rounded flex items-center justify-center transition-colors ${autoCenter ? "bg-[#007AFF]/20 text-[#007AFF]" : "hover:bg-[#3A3A3C] text-neutral-500"}`}
            title="Auto-center on mid price" aria-label="Auto-center on mid price" aria-pressed={autoCenter}
          >
            <Crosshair className="w-3 h-3" />
          </button>
        </div>

        {/* Columns Header */}
        <div className="dom-row items-center w-full px-2 py-1 text-[10px] font-mono text-neutral-500 uppercase tracking-wider bg-[#1C1C1E] shrink-0 border-b border-[#2C2C2E]">

          <div className="min-w-0 text-right">Bids</div>
          <div className="flex-1 text-center">Price</div>
          <div className="min-w-0 text-left">Asks</div>

          <div className="min-w-0 text-center" title="Recent Traded Volume">Traded</div>
        </div>

        {/* Content Container */}
        <div 
          ref={scrollRef}
          className="flex-1 overflow-y-auto no-scrollbar relative"
          onWheel={() => setAutoCenter(false)}
          onTouchMove={() => setAutoCenter(false)}
        >
          {!dom || sortedLevels.length === 0 ? (
            <div className="flex items-center justify-center h-full text-sm text-neutral-500 font-mono">
              Waiting for DOM...
            </div>
          ) : (
            <div style={{ height: sortedLevels.length * ROW_HEIGHT, position: "relative" }}>
              {sortedLevels.map((level, idx) => (
                <div key={`${level.price}-${idx}`} style={{ position: "absolute", top: idx * ROW_HEIGHT, left: 0, right: 0 }}>
                  <LadderRow 
                    level={level} 
                    isBestBid={level.price === dom.best_bid}
                    isBestAsk={level.price === dom.best_ask}
                    onStage={stage}
                  />
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </PanelFrame>
  );
}
