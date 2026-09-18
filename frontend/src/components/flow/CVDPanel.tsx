import { useMemo } from "react";
import { useFlowStore } from "@/lib/flow/useFlowStore";
import { PanelFrame } from "./PanelFrame";
import {
  ComposedChart,
  Line,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Cell,
  ReferenceLine
} from "recharts";
import { formatTimestampIST, formatCompactNumber } from "@/lib/flow/flowFormat";

export function CVDPanel({ symbol }: { symbol: string }) {
  const state = useFlowStore();
  
  const data = useMemo(() => {
    const bars = state.bars["1m"] || [];
    
    return bars.map(bar => ({
      time: bar.open_time,
      timeStr: formatTimestampIST(bar.open_time),
      cvd: bar.cumulative_delta,
      delta: bar.delta,
      vwap: state.metrics?.vwap || null, // We could pull historical vwap if we had it per bar, for now just delta
      isForming: !bar.is_closed,
    }));
  }, [state.bars, state.metrics?.vwap]);

  return (
    <PanelFrame title="CVD & Delta" symbol={symbol} health={state.health}>
      <div className="flex flex-col h-full w-full">
        {data.length === 0 ? (
          <div className="flex-1 flex items-center justify-center text-sm text-neutral-500 font-mono">
            Waiting for bar data...
          </div>
        ) : (
          <>
            {/* CVD Line Chart (Top pane) */}
            <div className="flex-[2] min-h-0 border-b border-[#2C2C2E] p-2">
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart data={data} margin={{ top: 5, right: 0, left: 0, bottom: 0 }}>
                  <XAxis dataKey="timeStr" hide />
                  <YAxis 
                    domain={["auto", "auto"]} 
                    orientation="right" 
                    tick={{ fontSize: 10, fill: "#8E8E93" }} 
                    tickFormatter={formatCompactNumber}
                    axisLine={false}
                    tickLine={false}
                    width={40}
                  />
                  <Tooltip
                    contentStyle={{ backgroundColor: "#1C1C1E", borderColor: "#3A3A3C", borderRadius: 4, fontSize: 12 }}
                    itemStyle={{ color: "#F2F2F7" }}
                    labelStyle={{ color: "#8E8E93", marginBottom: 4 }}
                  />
                  <ReferenceLine y={0} stroke="#3A3A3C" strokeDasharray="3 3" />
                  <Line
                    type="monotone"
                    dataKey="cvd"
                    stroke="#007AFF"
                    strokeWidth={2}
                    dot={false}
                    isAnimationActive={false}
                  />
                </ComposedChart>
              </ResponsiveContainer>
            </div>

            {/* Delta Bar Chart (Bottom pane) */}
            <div className="flex-1 min-h-0 p-2">
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart data={data} margin={{ top: 0, right: 0, left: 0, bottom: 5 }}>
                  <XAxis 
                    dataKey="timeStr" 
                    tick={{ fontSize: 10, fill: "#8E8E93" }} 
                    axisLine={false} 
                    tickLine={false}
                    minTickGap={30}
                  />
                  <YAxis 
                    orientation="right" 
                    tick={{ fontSize: 10, fill: "#8E8E93" }} 
                    tickFormatter={formatCompactNumber}
                    axisLine={false}
                    tickLine={false}
                    width={40}
                  />
                  <Tooltip
                    contentStyle={{ backgroundColor: "#1C1C1E", borderColor: "#3A3A3C", borderRadius: 4, fontSize: 12 }}
                    itemStyle={{ color: "#F2F2F7" }}
                    labelStyle={{ color: "#8E8E93", marginBottom: 4 }}
                    cursor={{ fill: "#2C2C2E" }}
                  />
                  <ReferenceLine y={0} stroke="#3A3A3C" />
                  <Bar dataKey="delta" isAnimationActive={false}>
                    {data.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={entry.delta > 0 ? "#34C759" : entry.delta < 0 ? "#FF453A" : "#8E8E93"} />
                    ))}
                  </Bar>
                </ComposedChart>
              </ResponsiveContainer>
            </div>
          </>
        )}
      </div>
    </PanelFrame>
  );
}
