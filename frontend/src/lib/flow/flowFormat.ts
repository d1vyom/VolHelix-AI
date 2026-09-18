export function formatCompactNumber(num: number): string {
  if (num >= 1e9) return (num / 1e9).toFixed(2) + "B";
  if (num >= 1e6) return (num / 1e6).toFixed(2) + "M";
  if (num >= 1e3) return (num / 1e3).toFixed(2) + "K";
  return num.toFixed(2);
}

export function formatPrice(price: number, precision: number = 2): string {
  return price.toLocaleString("en-US", {
    minimumFractionDigits: precision,
    maximumFractionDigits: precision,
  });
}

export function formatQty(qty: number, precision: number = 4): string {
  return qty.toLocaleString("en-US", {
    minimumFractionDigits: 0,
    maximumFractionDigits: precision,
  });
}

export function formatTimestampIST(ts: number | string): string {
  const d = new Date(ts);
  return d.toLocaleTimeString("en-IN", {
    timeZone: "Asia/Kolkata",
    hour12: false,
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

export function getDeltaColor(delta: number): string {
  if (delta > 0) return "text-green-500";
  if (delta < 0) return "text-red-500";
  return "text-gray-400";
}

export function roundToTickGroup(price: number, tickGroup: number): number {
  return Math.floor(price / tickGroup) * tickGroup;
}
