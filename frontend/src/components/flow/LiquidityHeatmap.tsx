import { useRef, useEffect, useState } from "react";
import { useFlowStore } from "@/lib/flow/useFlowStore";
import { PanelFrame } from "./PanelFrame";

export function LiquidityHeatmap({ symbol }: { symbol: string }) {
  const state = useFlowStore();
  const heatmapFrames = state.heatmapFrames || [];
  
  const canvasRef = useRef<HTMLCanvasElement>(null);
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

  // Render loop
  useEffect(() => {
    if (!canvasRef.current || dimensions.width === 0 || dimensions.height === 0 || heatmapFrames.length === 0) return;
    
    const ctx = canvasRef.current.getContext("2d");
    if (!ctx) return;
    
    const dpr = window.devicePixelRatio || 1;
    canvasRef.current.width = dimensions.width * dpr;
    canvasRef.current.height = dimensions.height * dpr;
    ctx.scale(dpr, dpr);
    
    const w = dimensions.width;
    const h = dimensions.height;
    
    // Clear
    ctx.fillStyle = "#121214";
    ctx.fillRect(0, 0, w, h);
    
    // Get min/max prices from all frames to scale Y axis
    let minPrice = Infinity;
    let maxPrice = -Infinity;
    let maxSize = 0;
    
    for (const frame of heatmapFrames) {
      for (const [price, bidSz, askSz] of frame.levels) {
        if (price < minPrice) minPrice = price;
        if (price > maxPrice) maxPrice = price;
        const total = bidSz + askSz;
        if (total > maxSize) maxSize = total;
      }
    }
    
    if (minPrice === Infinity || maxSize === 0) return;
    
    // Expand bounds slightly
    const range = maxPrice - minPrice;
    maxPrice += range * 0.05;
    minPrice -= range * 0.05;
    const yRange = maxPrice - minPrice;
    
    const colWidth = Math.max(2, w / Math.max(1, heatmapFrames.length));
    
    // Use 99th percentile for maxSize normalization (simplified here using a fraction of max)
    const normSize = maxSize * 0.8;
    
    // Draw frames
    for (let i = 0; i < heatmapFrames.length; i++) {
      const frame = heatmapFrames[i];
      const x = w - (heatmapFrames.length - i) * colWidth;
      
      for (const [price, bidSz, askSz] of frame.levels) {
        const y = h - ((price - minPrice) / yRange) * h;
        
        // Block height
        const bh = Math.max(1, h / (yRange / (frame.levels[1]?.[0] - frame.levels[0]?.[0] || 1)));
        
        const sz = bidSz + askSz;
        if (sz === 0) continue;
        
        const intensity = Math.min(1, sz / normSize);
        
        // Hue: bids green (120), asks red (0). If both, blend (unlikely at exact same price bucket).
        if (bidSz > 0) {
          ctx.fillStyle = `rgba(52, 199, 89, ${intensity})`; // #34C759
        } else {
          ctx.fillStyle = `rgba(255, 69, 58, ${intensity})`; // #FF453A
        }
        
        ctx.fillRect(x, y - bh/2, colWidth + 1, bh);
      }
    }
    
    // Overlay current price line (if we had it, typically we do via metrics)
    if (state.metrics?.price) {
      const y = h - ((state.metrics.price - minPrice) / yRange) * h;
      ctx.strokeStyle = "rgba(255, 255, 255, 0.5)";
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(w, y);
      ctx.stroke();
    }
    
  }, [state.heatmapFrames, dimensions, state.metrics?.price]);

  return (
    <PanelFrame title="Liquidity Heatmap" symbol={symbol} health={state.health}>
      <div className="flex flex-col h-full w-full bg-[#121214]">
        <div className="flex-1 relative overflow-hidden" ref={containerRef}>
          {heatmapFrames.length === 0 ? (
            <div className="flex items-center justify-center h-full text-sm text-neutral-500 font-mono">
              Waiting for heatmap...
            </div>
          ) : (
            <canvas 
              ref={canvasRef} 
              style={{ width: dimensions.width, height: dimensions.height, display: 'block' }}
            />
          )}
        </div>
      </div>
    </PanelFrame>
  );
}
