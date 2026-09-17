import { useRef, useEffect, useState } from "react";
import { useFlowStore } from "@/lib/flow/useFlowStore";
import { PanelFrame } from "./PanelFrame";
import { formatCompactNumber, formatTimestampIST } from "@/lib/flow/flowFormat";

export function FootprintChart({ symbol }: { symbol: string }) {
  const state = useFlowStore();
  const bars = state.bars["1m"] || [];
  const allBars = bars;
  
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [dimensions, setDimensions] = useState({ width: 0, height: 0 });
  const [clusterMode, setClusterMode] = useState<"BID_ASK" | "DELTA" | "VOLUME">("BID_ASK");

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

  useEffect(() => {
    if (!canvasRef.current || dimensions.width === 0 || dimensions.height === 0 || allBars.length === 0) return;
    
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
    
    // Calculate global min/max price
    let minPrice = Infinity;
    let maxPrice = -Infinity;
    let maxCellVol = 0;
    
    for (const bar of allBars) {
      if (bar.low < minPrice) minPrice = bar.low;
      if (bar.high > maxPrice) maxPrice = bar.high;
      for (const cell of bar.cells) {
        if (cell.total_volume > maxCellVol) maxCellVol = cell.total_volume;
      }
    }
    
    if (minPrice === Infinity) return;
    
    const priceRange = Math.max(1, maxPrice - minPrice);
    const tickSize = allBars[0]?.cells[1] 
      ? allBars[0].cells[1].price - allBars[0].cells[0].price 
      : priceRange / 10;
      
    // Add margin
    maxPrice += tickSize * 2;
    minPrice -= tickSize * 2;
    const renderRange = maxPrice - minPrice;
    
    // Footer height for delta/vol stats
    const footerH = 40;
    const chartH = h - footerH;
    
    // Bar width
    const minColWidth = 70;
    const colWidth = Math.max(minColWidth, (w - 60) / Math.max(1, allBars.length));
    
    // Price to Y
    const getY = (price: number) => {
      return chartH - ((price - minPrice) / renderRange) * chartH;
    };
    
    const cellH = Math.max(10, (tickSize / renderRange) * chartH);
    
    ctx.font = "10px monospace";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";

    for (let i = 0; i < allBars.length; i++) {
      const bar = allBars[i];
      const xCenter = w - 60 - (allBars.length - i - 0.5) * colWidth;
      
      // Draw candle wick
      const highY = getY(bar.high);
      const lowY = getY(bar.low);
      ctx.strokeStyle = bar.close >= bar.open ? "rgba(52, 199, 89, 0.3)" : "rgba(255, 69, 58, 0.3)";
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(xCenter, highY);
      ctx.lineTo(xCenter, lowY);
      ctx.stroke();

      // Cells
      for (const cell of bar.cells) {
        const y = getY(cell.price) - cellH / 2;
        
        // Intensity bg
        const intensity = maxCellVol > 0 ? cell.total_volume / maxCellVol : 0;
        ctx.fillStyle = `rgba(0, 122, 255, ${intensity * 0.3})`;
        ctx.fillRect(xCenter - colWidth/2 + 2, y, colWidth - 4, cellH - 1);
        
        // Text
        if (clusterMode === "BID_ASK") {
          ctx.fillStyle = cell.sell_volume > cell.buy_volume ? "#FF453A" : "#8E8E93";
          ctx.textAlign = "right";
          ctx.fillText(formatCompactNumber(cell.sell_volume), xCenter - 2, y + cellH/2);
          
          ctx.fillStyle = cell.buy_volume > cell.sell_volume ? "#34C759" : "#8E8E93";
          ctx.textAlign = "left";
          ctx.fillText(formatCompactNumber(cell.buy_volume), xCenter + 2, y + cellH/2);
          
          // Imbalance highlights
          if (cell.buy_imbalance) {
            ctx.fillStyle = "#34C759";
            ctx.fillRect(xCenter - colWidth/2 + 2, y, 3, cellH - 1);
          }
          if (cell.sell_imbalance) {
            ctx.fillStyle = "#FF453A";
            ctx.fillRect(xCenter - 2, y, 3, cellH - 1); // Not exact right edge to avoid clutter
          }
        } else if (clusterMode === "DELTA") {
          ctx.fillStyle = cell.delta > 0 ? "#34C759" : cell.delta < 0 ? "#FF453A" : "#8E8E93";
          ctx.textAlign = "center";
          ctx.fillText(formatCompactNumber(cell.delta), xCenter, y + cellH/2);
        } else if (clusterMode === "VOLUME") {
          ctx.fillStyle = "#F2F2F7";
          ctx.textAlign = "center";
          ctx.fillText(formatCompactNumber(cell.total_volume), xCenter, y + cellH/2);
        }
      }
      
      // POC Highlight
      if (bar.poc_price) {
        ctx.strokeStyle = "rgba(255, 159, 10, 0.5)"; // Amber
        ctx.lineWidth = 1;
        ctx.strokeRect(xCenter - colWidth/2 + 2, getY(bar.poc_price) - cellH/2, colWidth - 4, cellH - 1);
      }

      // Footer Stats
      ctx.fillStyle = bar.delta > 0 ? "#34C759" : "#FF453A";
      ctx.textAlign = "center";
      ctx.fillText(`Δ ${formatCompactNumber(bar.delta)}`, xCenter, chartH + 15);
      
      ctx.fillStyle = "#8E8E93";
      ctx.fillText(`V ${formatCompactNumber(bar.volume)}`, xCenter, chartH + 30);
      
      // Time string at bottom
      ctx.fillStyle = "#48484A";
      ctx.fillText(formatTimestampIST(bar.open_time), xCenter, chartH + 45);
    }
    
    // Draw Y axis labels
    ctx.fillStyle = "#1C1C1E";
    ctx.fillRect(w - 50, 0, 50, h);
    ctx.fillStyle = "#8E8E93";
    ctx.textAlign = "left";
    
    const tickSteps = 10;
    const yTickRange = renderRange / tickSteps;
    for(let i=0; i<=tickSteps; i++) {
      const p = minPrice + i * yTickRange;
      ctx.fillText(p.toFixed(2), w - 45, getY(p));
    }
    
    // Current price highlight
    if (state.metrics?.price) {
      const p = state.metrics.price;
      const py = getY(p);
      ctx.fillStyle = "#007AFF";
      ctx.fillRect(w - 50, py - 8, 50, 16);
      ctx.fillStyle = "#FFF";
      ctx.fillText(p.toFixed(2), w - 45, py);
      
      ctx.strokeStyle = "rgba(0, 122, 255, 0.3)";
      ctx.beginPath();
      ctx.moveTo(0, py);
      ctx.lineTo(w - 50, py);
      ctx.stroke();
    }
    
  }, [allBars, dimensions, clusterMode, state.metrics?.price]);

  return (
    <PanelFrame title="Footprint Chart" symbol={symbol} health={state.health}>
      <div className="flex flex-col h-full w-full bg-[#121214]">
        <div className="flex items-center px-2 py-1 text-[10px] font-mono text-neutral-400 bg-[#2C2C2E] border-b border-[#3A3A3C] shrink-0 gap-4">
          <select 
            value={clusterMode}
            onChange={(e) => setClusterMode(e.target.value as any)}
            className="bg-transparent text-white outline-none cursor-pointer"
          >
            <option value="BID_ASK">BID/ASK</option>
            <option value="DELTA">DELTA</option>
            <option value="VOLUME">VOLUME</option>
          </select>
        </div>
        <div className="flex-1 relative overflow-hidden" ref={containerRef}>
          {allBars.length === 0 ? (
             <div className="flex items-center justify-center h-full text-sm text-neutral-500 font-mono">
             Waiting for footprint...
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
