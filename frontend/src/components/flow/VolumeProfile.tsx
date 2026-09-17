import { useRef, useEffect, useState, useMemo } from "react";
import { useFlowStore } from "@/lib/flow/useFlowStore";
import { PanelFrame } from "./PanelFrame";
import { VolumeProfileSnapshot } from "@/lib/flow/flowTypes";

export function VolumeProfile({ symbol }: { symbol: string }) {
  const state = useFlowStore();
  const profile = state.profile;

  const containerRef = useRef<HTMLDivElement>(null);
  const [dimensions, setDimensions] = useState({ width: 0, height: 0 });

  // Handle resize
  useEffect(() => {
    if (!containerRef.current) return;
    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        setDimensions({
          width: entry.contentRect.width,
          height: entry.contentRect.height,
        });
      }
    });
    observer.observe(containerRef.current);
    return () => observer.disconnect();
  }, []);

  return (
    <PanelFrame title="Volume Profile" symbol={symbol} health={state.health}>
      <div className="flex flex-col h-full w-full bg-[#1C1C1E]">
        {/* Header/Controls */}
        <div className="flex items-center px-2 py-1 text-[10px] font-mono text-neutral-400 bg-[#2C2C2E] border-b border-[#3A3A3C] shrink-0 gap-4">
          <div className="flex gap-2">
            <span className="text-white cursor-pointer hover:text-[#007AFF]">SESSION</span>
            <span className="cursor-pointer hover:text-[#007AFF]">VISIBLE</span>
          </div>
          <div className="flex-1" />
          {profile && <div>TOTAL: {profile.total_volume.toFixed(0)}</div>}
        </div>

        {/* Content */}
        <div className="flex-1 relative overflow-hidden" ref={containerRef}>
          {!profile || profile.levels.length === 0 ? (
            <div className="flex items-center justify-center h-full text-sm text-neutral-500 font-mono">
              Waiting for profile...
            </div>
          ) : (
            <ProfileSVG profile={profile} width={dimensions.width} height={dimensions.height} />
          )}
        </div>
      </div>
    </PanelFrame>
  );
}

function ProfileSVG({ profile, width, height }: { profile: VolumeProfileSnapshot; width: number; height: number }) {
  if (width === 0 || height === 0) return null;

  const { levels, poc_price, vah, val } = profile;
  
  // Sort levels by price ascending (if not already)
  const sortedLevels = [...levels].sort((a, b) => b.price - a.price); // Descending for Y rendering (top is highest price)

  const minPrice = sortedLevels[sortedLevels.length - 1].price;
  const maxPrice = sortedLevels[0].price;
  const priceRange = maxPrice - minPrice;
  
  // Prevent div by zero if there's only 1 level
  const yScaling = priceRange > 0 ? (height - 20) / priceRange : 1; 

  // Max volume for width scaling
  const maxVol = Math.max(...levels.map(l => l.total_volume));
  const wScaling = maxVol > 0 ? (width - 60) / maxVol : 1; // Leave 60px for price labels

  // Map price to Y coordinate
  const getY = (price: number) => {
    return 10 + (maxPrice - price) * yScaling;
  };

  const levelHeight = Math.max(1, (height - 20) / Math.max(1, levels.length));

  return (
    <svg width={width} height={height} className="block">
      {/* VAH/VAL Background Band */}
      {vah > 0 && val > 0 && (
        <rect
          x={0}
          y={getY(vah)}
          width={width - 50}
          height={Math.max(1, getY(val) - getY(vah))}
          fill="#007AFF"
          fillOpacity={0.05}
        />
      )}

      {/* Levels */}
      {sortedLevels.map((lvl, i) => {
        const y = getY(lvl.price);
        const buyW = lvl.buy_volume * wScaling;
        const sellW = lvl.sell_volume * wScaling;
        
        return (
          <g key={lvl.price}>
            {/* Sell Volume (Red) */}
            <rect
              x={0}
              y={y - levelHeight / 2}
              width={sellW}
              height={levelHeight * 0.8}
              fill="#FF453A"
              fillOpacity={lvl.in_value_area ? 0.7 : 0.3}
            />
            {/* Buy Volume (Green) */}
            <rect
              x={sellW}
              y={y - levelHeight / 2}
              width={buyW}
              height={levelHeight * 0.8}
              fill="#34C759"
              fillOpacity={lvl.in_value_area ? 0.7 : 0.3}
            />
          </g>
        );
      })}

      {/* POC Line */}
      {poc_price > 0 && (
        <line
          x1={0}
          y1={getY(poc_price)}
          x2={width - 50}
          y2={getY(poc_price)}
          stroke="#FF9F0A"
          strokeWidth={1}
          strokeDasharray="4 2"
        />
      )}

      {/* Naked POCs */}
      {profile.naked_pocs.map((price, i) => (
        <line
          key={`npoc-${i}`}
          x1={0}
          y1={getY(price)}
          x2={width}
          y2={getY(price)}
          stroke="#FF9F0A"
          strokeWidth={1}
          strokeDasharray="2 4"
        />
      ))}

      {/* Price Axis Labels (Right side) */}
      <g className="font-mono text-[9px] fill-neutral-400">
        {/* Draw a few price ticks */}
        {[maxPrice, (maxPrice+minPrice)/2, minPrice].map((p, i) => (
          p > 0 && (
            <text key={i} x={width - 45} y={getY(p) + 3}>
              {p.toFixed(2)}
            </text>
          )
        ))}
        {poc_price > 0 && (
          <text x={width - 45} y={getY(poc_price) + 3} fill="#FF9F0A" fontWeight="bold">
            {poc_price.toFixed(2)}
          </text>
        )}
      </g>
    </svg>
  );
}
