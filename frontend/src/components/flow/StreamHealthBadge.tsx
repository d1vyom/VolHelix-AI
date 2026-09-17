import { StreamHealth } from "@/lib/flow/flowTypes";
import { Activity, AlertTriangle, XCircle, Slash } from "lucide-react";

export function StreamHealthBadge({ health }: { health?: StreamHealth | null }) {
  if (!health) {
    return (
      <div className="flex items-center gap-1 text-[10px] uppercase font-mono font-bold px-1.5 py-0.5 rounded bg-[#2C2C2E] text-neutral-500">
        <Slash className="w-3 h-3" />
        NO DATA
      </div>
    );
  }

  const { status, lag_ms, reconnects, book_resyncs, gap_events } = health;

  let colorClass = "text-neutral-500 bg-[#2C2C2E]";
  let Icon = Slash;
  let label = "DISABLED";

  if (status === "LIVE") {
    colorClass = "text-[#34C759] bg-[#34C759]/10";
    Icon = Activity;
    label = `${lag_ms}ms`;
  } else if (status === "DEGRADED") {
    colorClass = "text-[#FF9F0A] bg-[#FF9F0A]/10";
    Icon = AlertTriangle;
    label = "DEGRADED";
  } else if (status === "DISCONNECTED") {
    colorClass = "text-[#FF453A] bg-[#FF453A]/10";
    Icon = XCircle;
    label = "OFFLINE";
  }

  // Tooltip text
  const title = `Streams: ${health.streams.join(", ")}
Reconnects: ${reconnects}
Book Resyncs: ${book_resyncs}
Trade Gaps: ${gap_events}
Last Event Age: ${lag_ms}ms
Status: ${status}`;

  return (
    <div
      title={title}
      className={`flex items-center gap-1 text-[10px] uppercase font-mono font-bold px-1.5 py-0.5 rounded cursor-help transition-colors ${colorClass}`}
    >
      <Icon className="w-3 h-3" />
      {label}
    </div>
  );
}
