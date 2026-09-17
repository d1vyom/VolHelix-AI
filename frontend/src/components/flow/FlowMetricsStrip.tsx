import { useFlowStore } from "@/lib/flow/useFlowStore";
import { StreamHealthBadge } from "./StreamHealthBadge";
import { formatCompactNumber } from "@/lib/flow/flowFormat";
import { FlowMetrics } from "@/lib/flow/flowTypes";

function MetricTile({ label, value, tooltip, colorClass = "text-neutral-200" }: { label: string; value: React.ReactNode; tooltip: string; colorClass?: string }) {
  return (
    <div className="flex flex-col px-3 py-1 border-r border-[#2C2C2E] last:border-r-0 min-w-0 shrink-0 group" title={tooltip}>
      <span className="text-[10px] text-neutral-500 font-medium uppercase tracking-wider whitespace-nowrap">{label}</span>
      <span className={`text-xs font-mono font-bold whitespace-nowrap ${colorClass}`}>
        {value !== undefined && value !== null ? value : "—"}
      </span>
    </div>
  );
}

export function FlowMetricsStrip({ symbol }: { symbol: string }) {
  const state = useFlowStore();
  const metrics = state.metrics;
  const health = state.health;

  return (
    <div className="flex items-center w-full bg-[#1C1C1E] border border-[#2C2C2E] rounded-md overflow-x-auto no-scrollbar">
      {/* Price */}
      <MetricTile 
        label="Price" 
        value={metrics?.price?.toFixed(2) || "—"} 
        tooltip="Last traded price" 
        colorClass="text-neutral-100" 
      />
      
      {/* Bar Delta */}
      <MetricTile 
        label="Δ Bar" 
        value={metrics ? `${metrics.bar_delta > 0 ? "+" : ""}${formatCompactNumber(metrics.bar_delta)}` : "—"} 
        tooltip="Net aggressor volume (Buy - Sell) for the current bar"
        colorClass={!metrics ? "" : metrics.bar_delta > 0 ? "text-[#34C759]" : metrics.bar_delta < 0 ? "text-[#FF453A]" : "text-neutral-400"}
      />

      {/* CVD Session */}
      <MetricTile 
        label="CVD (Session)" 
        value={metrics ? `${metrics.session_cvd > 0 ? "+" : ""}${formatCompactNumber(metrics.session_cvd)}` : "—"} 
        tooltip="Cumulative Volume Delta anchored at session start"
        colorClass={!metrics ? "" : metrics.session_cvd > 0 ? "text-[#34C759]" : metrics.session_cvd < 0 ? "text-[#FF453A]" : "text-neutral-400"}
      />

      {/* CVD Slope */}
      <MetricTile 
        label="CVD Slope/m" 
        value={metrics?.cvd_slope ? `${metrics.cvd_slope > 0 ? "+" : ""}${formatCompactNumber(metrics.cvd_slope)}/m` : "—"} 
        tooltip="Rate of change of CVD over the last 30 minutes"
        colorClass={!metrics ? "" : metrics.cvd_slope > 0 ? "text-[#34C759]" : metrics.cvd_slope < 0 ? "text-[#FF453A]" : "text-neutral-400"}
      />

      {/* Buy/Sell Ratio */}
      <MetricTile 
        label="B/S Ratio (1m)" 
        value={metrics?.buy_sell_ratio ? `${metrics.buy_sell_ratio.toFixed(2)}x` : "—"} 
        tooltip="Rolling 1-minute aggressor buy volume vs sell volume"
        colorClass={!metrics ? "" : metrics.buy_sell_ratio > 1.2 ? "text-[#34C759]" : metrics.buy_sell_ratio < 0.8 ? "text-[#FF453A]" : "text-neutral-200"}
      />

      {/* Aggression Index */}
      <MetricTile 
        label="Aggression" 
        value={metrics?.aggression_index !== undefined ? `${(metrics.aggression_index * 100).toFixed(0)}%` : "—"} 
        tooltip="Share of volume from large whale prints in the last minute"
        colorClass={!metrics ? "" : metrics.aggression_index > 0.5 ? "text-[#FF9F0A]" : "text-neutral-200"}
      />

      {/* Book Imbalance */}
      <MetricTile 
        label="Book Imb" 
        value={metrics?.book_imbalance !== undefined ? `${(metrics.book_imbalance * 100).toFixed(0)}%` : "—"} 
        tooltip="Normalized order book depth imbalance (-100% to +100%)"
        colorClass={!metrics ? "" : metrics.book_imbalance > 0.1 ? "text-[#34C759]" : metrics.book_imbalance < -0.1 ? "text-[#FF453A]" : "text-neutral-400"}
      />

      {/* Spread */}
      <MetricTile 
        label="Spread" 
        value={metrics?.spread_bps !== undefined ? `${metrics.spread_bps.toFixed(1)} bps` : "—"} 
        tooltip="Bid-ask spread in basis points"
        colorClass={!metrics ? "" : metrics.spread_bps > 5 ? "text-[#FF9F0A]" : "text-neutral-400"}
      />

      {/* Price vs Value */}
      <MetricTile 
        label="Price vs Value" 
        value={metrics?.price_vs_value ? metrics.price_vs_value.replace("_", " ") : "—"} 
        tooltip="Current price relative to the Value Area (VAH/VAL)"
        colorClass={!metrics ? "" : metrics.price_vs_value === "ABOVE_VALUE" ? "text-[#34C759]" : metrics.price_vs_value === "BELOW_VALUE" ? "text-[#FF453A]" : "text-neutral-400"}
      />

      {/* Stacked Imbalance Bias */}
      <MetricTile 
        label="Stacked Bias" 
        value={metrics?.stacked_imbalance_bias || "—"} 
        tooltip="Direction of recent stacked imbalances"
        colorClass={!metrics ? "" : metrics.stacked_imbalance_bias === "BUY" ? "text-[#34C759]" : metrics.stacked_imbalance_bias === "SELL" ? "text-[#FF453A]" : "text-neutral-400"}
      />

      {/* Absorption */}
      <MetricTile 
        label="Absorption" 
        value={metrics?.absorption_flag ? metrics.absorption_flag.replace("_ABSORBED", "") : "NONE"} 
        tooltip="Detects if aggressive market orders are being absorbed by passive limit orders"
        colorClass={!metrics ? "" : metrics.absorption_flag === "BUY_ABSORBED" ? "text-[#FF453A]" : metrics.absorption_flag === "SELL_ABSORBED" ? "text-[#34C759]" : "text-neutral-500"}
      />
      
      <div className="flex-1" /> {/* Spacer */}
      
      {/* Stream Health */}
      <div className="flex items-center px-3">
        <StreamHealthBadge health={health} />
      </div>
    </div>
  );
}
