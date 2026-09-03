import { Regime } from "./types";

export function formatCurrency(val: number, includeSign = false): string {
  const formatted = Math.abs(val).toLocaleString("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  if (includeSign && val > 0) return `+${formatted}`;
  if (val < 0) return `-${formatted}`;
  return formatted;
}

export function formatPercent(val: number, includeSign = false): string {
  const formatted = `${(Math.abs(val) * 100).toFixed(1)}%`;
  if (includeSign && val > 0) return `+${formatted}`;
  if (val < 0) return `-${formatted}`;
  return formatted;
}

export function formatDate(isoStr: string): string {
  try {
    return new Date(isoStr).toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return isoStr;
  }
}

export function getRegimeColor(regime: Regime | string): string {
  switch (regime) {
    case "LOW_VOL":
      return "#3b82f6"; // Blue
    case "NORMAL":
      return "#10b981"; // Emerald
    case "ELEVATED":
      return "#f59e0b"; // Amber
    case "SQUEEZE":
      return "#ec4899"; // Pink
    case "CRISIS":
      return "#ef4444"; // Red
    default:
      return "#10b981";
  }
}
