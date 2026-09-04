"use client";

import { useState, useRef, useMemo, useCallback, useEffect, memo } from "react";
import { AlpacaBar } from "../lib/api";
import { ZoomIn, ZoomOut, RotateCcw } from "lucide-react";

interface CandlestickChartProps {
  data: AlpacaBar[];
  chartType?: "CANDLE" | "LINE";
  chartInterval?: string;
  currentPrice?: number;
}

export const CandlestickChart = memo(function CandlestickChart({
  data,
  chartType = "CANDLE",
  chartInterval = "1H",
  currentPrice,
}: CandlestickChartProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const wheelHandlerRef = useRef<((e: WheelEvent) => void) | null>(null);

  const [zoomLevel, setZoomLevel] = useState<number>(1.0);
  const [panOffset, setPanOffset] = useState<number>(0);
  const [isDragging, setIsDragging] = useState<boolean>(false);
  const [dragStartX, setDragStartX] = useState<number>(0);
  const [dragStartOffset, setDragStartOffset] = useState<number>(0);
  const [mousePos, setMousePos] = useState<{ x: number; y: number } | null>(null);
  const [timeNow, setTimeNow] = useState<number>(0);

  // 1-second interval to update candle close countdown
  useEffect(() => {
    const initial = setTimeout(() => setTimeNow(Date.now()), 0);
    const timer = setInterval(() => setTimeNow(Date.now()), 1000);
    return () => {
      clearTimeout(initial);
      clearInterval(timer);
    };
  }, []);

  // Callback ref: guaranteed to attach native non-passive wheel listener as soon as DOM element mounts
  const setContainerRef = useCallback((node: HTMLDivElement | null) => {
    if (containerRef.current && wheelHandlerRef.current) {
      containerRef.current.removeEventListener("wheel", wheelHandlerRef.current);
      wheelHandlerRef.current = null;
    }
    containerRef.current = node;
    if (node) {
      const onWheelNative = (e: WheelEvent) => {
        e.preventDefault();
        e.stopPropagation();
        const delta = e.deltaY < 0 ? 0.15 : -0.15;
        setZoomLevel((z) => Math.max(0.4, Math.min(4.0, Number((z + delta).toFixed(2)))));
      };
      wheelHandlerRef.current = onWheelNative;
      node.addEventListener("wheel", onWheelNative, { passive: false });
    }
  }, []);

  // Compute slice of bars based on zoom and pan
  const totalBars = data.length;
  const visibleBars = useMemo(() => {
    if (!data || totalBars === 0) return [];
    const baseCount = Math.min(totalBars, 22);
    const count = Math.max(4, Math.min(totalBars, Math.round(baseCount / zoomLevel)));
    const maxOffset = totalBars - count;
    const clampedOffset = Math.max(0, Math.min(maxOffset, panOffset));
    const start = Math.max(0, totalBars - count - clampedOffset);
    const end = Math.min(totalBars, totalBars - clampedOffset);
    return data.slice(start, end);
  }, [data, totalBars, zoomLevel, panOffset]);

  // Live dynamic candle updating: the latest active candle adjusts size in real time with currentPrice
  const effectiveBars = useMemo(() => {
    if (!visibleBars || visibleBars.length === 0) return [];
    const barsCopy = [...visibleBars];
    if (currentPrice && currentPrice > 0 && panOffset === 0) {
      const lastIdx = barsCopy.length - 1;
      const original = barsCopy[lastIdx];
      // STRICT SAFETY GUARD:
      // Prevent cross-ticker race condition flash crashes/spikes!
      // If currentPrice deviates by more than 15% from the bar's close, it indicates a quote
      // from another symbol (e.g. AAPL $327 vs QQQ $718) arriving before the new bars have loaded.
      const deviation = Math.abs(currentPrice - original.close) / (original.close || 1);
      if (deviation <= 0.15) {
        barsCopy[lastIdx] = {
          ...original,
          close: currentPrice,
          high: Math.max(original.high, currentPrice),
          low: Math.min(original.low, currentPrice),
        };
      }
    }
    return barsCopy;
  }, [visibleBars, currentPrice, panOffset]);

  // Live price to use for permanent line
  const activeLivePrice = useMemo(() => {
    if (!effectiveBars || effectiveBars.length === 0) return currentPrice || 574.85;
    const lastClose = effectiveBars[effectiveBars.length - 1].close;
    if (currentPrice && currentPrice > 0) {
      const deviation = Math.abs(currentPrice - lastClose) / (lastClose || 1);
      if (deviation <= 0.15) {
        return currentPrice;
      }
    }
    return lastClose;
  }, [effectiveBars, currentPrice]);

  // Compute price boundaries for visible slice including active live price
  const { minPrice, priceRange } = useMemo(() => {
    if (!effectiveBars || effectiveBars.length === 0) {
      return { minPrice: 0, priceRange: 100 };
    }
    let min = Infinity;
    let max = -Infinity;
    for (const b of effectiveBars) {
      if (b.low < min) min = b.low;
      if (b.high > max) max = b.high;
    }
    if (activeLivePrice < min) min = activeLivePrice;
    if (activeLivePrice > max) max = activeLivePrice;

    const pad = (max - min) * 0.08 || 1;
    return {
      minPrice: min - pad,
      priceRange: (max + pad) - (min - pad),
    };
  }, [effectiveBars, activeLivePrice]);

  // Chart layout dimensions
  const height = 260;
  const paddingTop = 28;
  const paddingBottom = 26;
  const paddingRight = 92; // room for price + countdown badge
  const chartHeight = height - paddingBottom - paddingTop;
  const svgWidth = 800;
  const chartWidth = svgWidth - paddingRight;

  const priceToY = useCallback((price: number) => {
    if (priceRange <= 0) return chartHeight / 2 + paddingTop;
    return paddingTop + chartHeight - ((price - minPrice) / priceRange) * chartHeight;
  }, [priceRange, minPrice, chartHeight, paddingTop]);

  const yToPrice = useCallback((y: number) => {
    if (chartHeight <= 0) return minPrice;
    const clampedY = Math.max(paddingTop, Math.min(height - paddingBottom, y));
    const normalized = (chartHeight - (clampedY - paddingTop)) / chartHeight;
    return minPrice + normalized * priceRange;
  }, [chartHeight, paddingTop, height, paddingBottom, minPrice, priceRange]);

  // Horizontal Grid price levels (5 ticks)
  const priceTicks = useMemo(() => {
    const ticks = [];
    const count = 5;
    for (let i = 0; i < count; i++) {
      const p = minPrice + (priceRange / (count - 1)) * i;
      ticks.push({ price: p, y: priceToY(p) });
    }
    return ticks;
  }, [minPrice, priceRange, priceToY]);

  // Drag-to-pan handlers
  const handleMouseDown = (e: React.MouseEvent) => {
    if (e.button === 0) {
      setIsDragging(true);
      setDragStartX(e.clientX);
      setDragStartOffset(panOffset);
    }
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    if (!containerRef.current) return;
    const rect = containerRef.current.getBoundingClientRect();
    const clientX = e.clientX - rect.left;
    const clientY = e.clientY - rect.top;

    const scaleX = svgWidth / rect.width;
    const scaleY = height / rect.height;
    const svgX = clientX * scaleX;
    const svgY = clientY * scaleY;

    setMousePos({ x: svgX, y: svgY });

    if (isDragging) {
      const deltaScreenX = e.clientX - dragStartX;
      const barStepScreen = (rect.width - (paddingRight / svgWidth) * rect.width) / (effectiveBars.length || 1);
      const deltaBars = Math.round(deltaScreenX / barStepScreen);
      const maxOffset = totalBars - effectiveBars.length;
      setPanOffset(Math.max(0, Math.min(maxOffset, dragStartOffset - deltaBars)));
    }
  };

  const handleMouseUp = () => {
    setIsDragging(false);
  };

  const handleMouseLeave = () => {
    setIsDragging(false);
    setMousePos(null);
  };

  // Zoom control buttons
  const zoomIn = () => setZoomLevel((z) => Math.min(4.0, Number((z + 0.25).toFixed(2))));
  const zoomOut = () => setZoomLevel((z) => Math.max(0.4, Number((z - 0.25).toFixed(2))));
  const resetZoom = () => {
    setZoomLevel(1.0);
    setPanOffset(0);
  };

  if (!data || data.length === 0) {
    return (
      <div className="h-68 w-full flex items-center justify-center text-[#878996] font-mono text-xs">
        Loading real-time market data...
      </div>
    );
  }

  // Dynamic bar sizing across all zoom levels
  const barCount = effectiveBars.length;
  const virtualSlotCount = Math.max(barCount, Math.round(22 / zoomLevel));
  const barStep = chartWidth / virtualSlotCount;
  const candleBodyWidth = Math.max(3, Math.min(32, barStep * 0.75));

  // Determine hovered bar index based on freely movable mouseX
  let hoveredIdx = -1;
  if (mousePos && mousePos.x >= 0 && mousePos.x <= chartWidth) {
    hoveredIdx = Math.max(0, Math.min(barCount - 1, Math.floor(mousePos.x / barStep)));
  }
  const hoveredBar = hoveredIdx >= 0 && effectiveBars[hoveredIdx]
    ? effectiveBars[hoveredIdx]
    : effectiveBars[barCount - 1];

  // Calculate live closing countdown for current active candle
  const now = timeNow ? new Date(timeNow) : new Date();
  const currentHour = now.getHours();
  const currentMin = now.getMinutes();
  const currentSec = now.getSeconds();
  let hoursLeft = 0;
  let minsLeft = 59 - currentMin;
  const secsLeft = 59 - currentSec;

  if (chartInterval === "1m") {
    minsLeft = 0;
  } else if (chartInterval === "5m") {
    minsLeft = 4 - (currentMin % 5);
  } else if (chartInterval === "15m") {
    minsLeft = 14 - (currentMin % 15);
  } else if (chartInterval === "1H") {
    minsLeft = 59 - currentMin;
  } else if (chartInterval === "4H") {
    hoursLeft = 3 - (currentHour % 4);
    minsLeft = 59 - currentMin;
  } else if (chartInterval === "1D") {
    hoursLeft = 23 - currentHour;
    minsLeft = 59 - currentMin;
  }
  const countdownFormatted = hoursLeft > 0
    ? `${String(hoursLeft).padStart(2, "0")}:${String(minsLeft).padStart(2, "0")}:${String(secsLeft).padStart(2, "0")}`
    : `${String(minsLeft).padStart(2, "0")}:${String(secsLeft).padStart(2, "0")}`;

  // Price at hover cursor Y
  const cursorPrice = mousePos ? yToPrice(mousePos.y) : null;

  // OHLC metrics for Top HUD
  const change = hoveredBar ? hoveredBar.close - hoveredBar.open : 0;
  const changePct = hoveredBar && hoveredBar.open ? (change / hoveredBar.open) * 100 : 0;
  const isUp = change >= 0;

  // Build SVG Path for Line Mode
  let linePath = "";
  let areaPath = "";
  if (chartType === "LINE" && effectiveBars.length > 0) {
    effectiveBars.forEach((b, i) => {
      const x = (i + 0.5) * barStep;
      const y = priceToY(b.close);
      if (i === 0) {
        linePath += `M ${x} ${y}`;
        areaPath += `M ${x} ${y}`;
      } else {
        linePath += ` L ${x} ${y}`;
        areaPath += ` L ${x} ${y}`;
      }
    });
    const lastX = (effectiveBars.length - 0.5) * barStep;
    const firstX = 0.5 * barStep;
    const bottomY = height - paddingBottom;
    areaPath += ` L ${lastX} ${bottomY} L ${firstX} ${bottomY} Z`;
  }

  // Y coordinate of permanent live price line
  const livePriceY = priceToY(activeLivePrice);

  // Determine color of permanent crosshair based on current candle state (Red vs Green)
  const currentLiveBar = effectiveBars.length > 0 ? effectiveBars[effectiveBars.length - 1] : null;
  const isCurrentCandleRed = currentLiveBar ? currentLiveBar.close < currentLiveBar.open : false;
  const liveColor = isCurrentCandleRed ? "#ef454a" : "#00c087";
  const liveTextColor = isCurrentCandleRed ? "#ffffff" : "#121214";

  return (
    <div
      ref={setContainerRef}
      onMouseDown={handleMouseDown}
      onMouseMove={handleMouseMove}
      onMouseUp={handleMouseUp}
      onMouseLeave={handleMouseLeave}
      className={`relative w-full h-68 select-none font-mono text-xs overflow-hidden ${
        isDragging ? "cursor-grabbing" : "cursor-crosshair"
      }`}
    >
      {/* Top OHLC Indicator Banner */}
      {hoveredBar && (
        <div className="absolute top-1.5 left-3 z-10 flex flex-wrap items-center gap-3 text-[11px] pointer-events-none">
          <span className="text-[#878996]">Time: <strong className="text-[#f5f5f5]">{hoveredBar.time}</strong></span>
          <span className="text-[#878996]">O: <strong className="text-[#f5f5f5]">${hoveredBar.open.toFixed(2)}</strong></span>
          <span className="text-[#878996]">H: <strong className="text-[#f5f5f5]">${hoveredBar.high.toFixed(2)}</strong></span>
          <span className="text-[#878996]">L: <strong className="text-[#f5f5f5]">${hoveredBar.low.toFixed(2)}</strong></span>
          <span className="text-[#878996]">C: <strong className="text-[#f5f5f5]">${hoveredBar.close.toFixed(2)}</strong></span>
          <span className={`font-bold ${isUp ? "text-[#20b26c]" : "text-[#ef454a]"}`}>
            {isUp ? "+" : ""}${change.toFixed(2)} ({isUp ? "+" : ""}{changePct.toFixed(2)}%)
          </span>
          <span className="text-[#878996]">Vol: <strong className="text-[#20b26c]">{(hoveredBar.volume / 1000).toFixed(1)}K</strong></span>
        </div>
      )}

      {/* Floating Zoom & Pan Controls (Bottom-Left) */}
      <div className="absolute bottom-2 left-2 z-20 flex items-center gap-1 bg-[#18191f]/90 backdrop-blur-sm border border-[#26282f] p-0.5 rounded shadow-lg">
        <button
          onClick={zoomIn}
          className="p-1 rounded hover:bg-[#26282f] text-[#878996] hover:text-[#f7a600] transition-colors cursor-pointer"
          title="Zoom In (Scroll Up)"
        >
          <ZoomIn className="w-3.5 h-3.5" />
        </button>
        <button
          onClick={zoomOut}
          className="p-1 rounded hover:bg-[#26282f] text-[#878996] hover:text-[#f7a600] transition-colors cursor-pointer"
          title="Zoom Out (Scroll Down)"
        >
          <ZoomOut className="w-3.5 h-3.5" />
        </button>
        <button
          onClick={resetZoom}
          className="p-1 rounded hover:bg-[#26282f] text-[#878996] hover:text-[#f7a600] transition-colors cursor-pointer"
          title="Reset Zoom & Pan"
        >
          <RotateCcw className="w-3.5 h-3.5" />
        </button>
        <span className="px-1.5 text-[10px] text-[#f7a600] font-bold">
          {Math.round(zoomLevel * 100)}%
        </span>
      </div>

      {/* Main Interactive SVG Canvas */}
      <svg
        viewBox={`0 0 ${svgWidth} ${height}`}
        preserveAspectRatio="none"
        className="w-full h-full"
      >
        <defs>
          <linearGradient id="chartAreaGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor="#f7a600" stopOpacity={0.35} />
            <stop offset="95%" stopColor="#f7a600" stopOpacity={0.0} />
          </linearGradient>
        </defs>

        <rect width={svgWidth} height={height} fill="#121214" />

        {/* Horizontal Price Gridlines and Right Price Axis */}
        {priceTicks.map((tick, idx) => (
          <g key={idx}>
            <line
              x1={0}
              y1={tick.y}
              x2={chartWidth}
              y2={tick.y}
              stroke="#1f2128"
              strokeDasharray="3 3"
              strokeWidth={1}
            />
            <text
              x={chartWidth + 6}
              y={tick.y + 3}
              fill="#5e6673"
              fontSize={10}
              fontFamily="monospace"
            >
              ${tick.price.toFixed(0)}
            </text>
          </g>
        ))}

        {/* Chart Mode: Candlesticks vs. Line Curve */}
        {chartType === "CANDLE" ? (
          /* Candlesticks */
          <g>
            {effectiveBars.map((b, i) => {
              const x = (i + 0.5) * barStep;
              const yHigh = priceToY(b.high);
              const yLow = priceToY(b.low);
              const yOpen = priceToY(b.open);
              const yClose = priceToY(b.close);
              const candleUp = b.close >= b.open;
              const color = candleUp ? "#20b26c" : "#ef454a";
              const rectY = Math.min(yOpen, yClose);
              const rectH = Math.max(2, Math.abs(yOpen - yClose));

              return (
                <g key={i}>
                  {/* Upper & Lower Wick Line */}
                  <line
                    x1={x}
                    y1={yHigh}
                    x2={x}
                    y2={yLow}
                    stroke={color}
                    strokeWidth={1.5}
                  />

                  {/* Candle Solid Body */}
                  <rect
                    x={x - candleBodyWidth / 2}
                    y={rectY}
                    width={candleBodyWidth}
                    height={rectH}
                    fill={color}
                    rx={1}
                  />

                  {/* Time labels along the bottom */}
                  {i % Math.max(1, Math.floor(barCount / 6)) === 0 && (
                    <text
                      x={x}
                      y={height - 6}
                      fill="#5e6673"
                      fontSize={10}
                      textAnchor="middle"
                      fontFamily="monospace"
                    >
                      {b.time}
                    </text>
                  )}
                </g>
              );
            })}
          </g>
        ) : (
          /* Line / Area Chart */
          <g>
            <path d={areaPath} fill="url(#chartAreaGrad)" />
            <path d={linePath} fill="none" stroke="#f7a600" strokeWidth={2} />
            {effectiveBars.map((b, i) => {
              const x = (i + 0.5) * barStep;
              return (
                <g key={i}>
                  {i % Math.max(1, Math.floor(barCount / 6)) === 0 && (
                    <text
                      x={x}
                      y={height - 6}
                      fill="#5e6673"
                      fontSize={10}
                      textAnchor="middle"
                      fontFamily="monospace"
                    >
                      {b.time}
                    </text>
                  )}
                </g>
              );
            })}
          </g>
        )}

        {/* ========================================================================= */}
        {/* 1. PERMANENT LIVE PRICE CROSSHAIR (Matches candle color: Red or Green)    */}
        {/* ========================================================================= */}
        <g className="pointer-events-none">
          {/* Permanent Horizontal Line across the chart at live price */}
          <line
            x1={0}
            y1={livePriceY}
            x2={chartWidth}
            y2={livePriceY}
            stroke={liveColor}
            strokeDasharray="3 3"
            strokeWidth={1.2}
            opacity={0.85}
          />

          {/* Permanent Live Price + Candle Closing Countdown Badge on the Right Axis */}
          <rect
            x={chartWidth}
            y={Math.max(paddingTop, Math.min(height - paddingBottom - 26, livePriceY - 13))}
            width={paddingRight}
            height={26}
            fill={liveColor}
            rx={2}
            className="shadow-lg"
          />
          {/* Live Price Text */}
          <text
            x={chartWidth + 6}
            y={Math.max(paddingTop, Math.min(height - paddingBottom - 26, livePriceY - 13)) + 11}
            fill={liveTextColor}
            fontSize={11}
            fontWeight="bold"
            fontFamily="monospace"
          >
            {activeLivePrice.toFixed(2)}
          </text>
          {/* Live Candle Closing Countdown */}
          <text
            x={chartWidth + 6}
            y={Math.max(paddingTop, Math.min(height - paddingBottom - 26, livePriceY - 13)) + 22}
            fill={liveTextColor}
            fontSize={9}
            fontWeight="bold"
            fontFamily="monospace"
          >
            {countdownFormatted}
          </text>
        </g>

        {/* ========================================================================= */}
        {/* 2. HOVER INSPECTION CROSSHAIR (User Cursor with (+) Badge)               */}
        {/* ========================================================================= */}
        {mousePos && mousePos.x >= 0 && mousePos.x <= chartWidth && mousePos.y >= paddingTop && mousePos.y <= height - paddingBottom && (
          <g className="pointer-events-none">
            {/* Inspection Vertical Dotted Line */}
            <line
              x1={mousePos.x}
              y1={paddingTop}
              x2={mousePos.x}
              y2={height - paddingBottom}
              stroke="#878996"
              strokeDasharray="2 2"
              strokeWidth={1}
            />

            {/* Inspection Horizontal Dotted Line */}
            <line
              x1={0}
              y1={mousePos.y}
              x2={chartWidth}
              y2={mousePos.y}
              stroke="#878996"
              strokeDasharray="2 2"
              strokeWidth={1}
            />

            {/* Bottom Time Badge at Mouse X */}
            {hoveredBar && (
              <g>
                <rect
                  x={Math.max(2, Math.min(chartWidth - 66, mousePos.x - 33))}
                  y={height - 21}
                  width={66}
                  height={18}
                  fill="#26282f"
                  stroke="#363a45"
                  strokeWidth={1}
                  rx={2}
                />
                <text
                  x={Math.max(2, Math.min(chartWidth - 66, mousePos.x - 33)) + 33}
                  y={height - 8}
                  fill="#f5f5f5"
                  fontSize={10}
                  fontWeight="bold"
                  textAnchor="middle"
                  fontFamily="monospace"
                >
                  {hoveredBar.time}
                </text>
              </g>
            )}

            {/* Right Axis Inspection Badge with (+) Button as in User Screenshot */}
            {cursorPrice !== null && (
              <g>
                <rect
                  x={chartWidth}
                  y={Math.max(paddingTop, Math.min(height - paddingBottom - 18, mousePos.y - 9))}
                  width={paddingRight}
                  height={18}
                  fill="#26282f"
                  stroke="#474c59"
                  strokeWidth={1}
                  rx={2}
                  className="shadow-xl"
                />
                {/* (+) icon indicator */}
                <circle
                  cx={chartWidth + 8}
                  cy={Math.max(paddingTop, Math.min(height - paddingBottom - 18, mousePos.y - 9)) + 9}
                  r={4.5}
                  fill="#363a45"
                  stroke="#878996"
                  strokeWidth={1}
                />
                <line
                  x1={chartWidth + 6}
                  y1={Math.max(paddingTop, Math.min(height - paddingBottom - 18, mousePos.y - 9)) + 9}
                  x2={chartWidth + 10}
                  y2={Math.max(paddingTop, Math.min(height - paddingBottom - 18, mousePos.y - 9)) + 9}
                  stroke="#f5f5f5"
                  strokeWidth={1}
                />
                <line
                  x1={chartWidth + 8}
                  y1={Math.max(paddingTop, Math.min(height - paddingBottom - 18, mousePos.y - 9)) + 7}
                  x2={chartWidth + 8}
                  y2={Math.max(paddingTop, Math.min(height - paddingBottom - 18, mousePos.y - 9)) + 11}
                  stroke="#f5f5f5"
                  strokeWidth={1}
                />
                {/* Cursor Price text */}
                <text
                  x={chartWidth + 16}
                  y={Math.max(paddingTop, Math.min(height - paddingBottom - 18, mousePos.y - 9)) + 13}
                  fill="#f5f5f5"
                  fontSize={10}
                  fontWeight="bold"
                  fontFamily="monospace"
                >
                  {cursorPrice.toFixed(2)}
                </text>
              </g>
            )}
          </g>
        )}
      </svg>
    </div>
  );
});