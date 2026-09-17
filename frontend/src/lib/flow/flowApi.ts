import { safeJson } from "../api";
import { 
  StreamHealth, FootprintBar, TapeEntry, DomAnalytics, 
  HeatmapSnapshot, VolumeProfileSnapshot, FlowMetrics, CVDPoint
} from "./flowTypes";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "";

export interface FlowStatusResponse {
  enabled: boolean;
  reason?: string;
  symbols?: string[];
  health?: Record<string, StreamHealth>;
}

export async function getFlowStatus(): Promise<FlowStatusResponse> {
  const res = await fetch(`${API_BASE}/api/flow/status`);
  return await safeJson<FlowStatusResponse>(res, { enabled: false, reason: "Fetch failed" });
}

export interface FootprintResponse {
  symbol: string;
  interval: string;
  tick_group: number;
  bars: FootprintBar[];
}

export async function getFootprint(symbol: string, interval: string = "1m", limit: number = 60, tickGroup?: number): Promise<FootprintResponse | null> {
  let url = `${API_BASE}/api/flow/footprint?symbol=${encodeURIComponent(symbol)}&interval=${interval}&limit=${limit}`;
  if (tickGroup !== undefined) url += `&tick_group=${tickGroup}`;
  const res = await fetch(url);
  const data = await safeJson<{ success?: boolean } & FootprintResponse>(res, {} as { success?: boolean } & FootprintResponse);
  if (data.success === false) return null;
  return data;
}

export async function getDom(symbol: string, levels: number = 20, tickGroup?: number): Promise<DomAnalytics | null> {
  let url = `${API_BASE}/api/flow/dom?symbol=${encodeURIComponent(symbol)}&levels=${levels}`;
  if (tickGroup !== undefined) url += `&tick_group=${tickGroup}`;
  const res = await fetch(url);
  const data = await safeJson<{ success?: boolean } & DomAnalytics>(res, {} as { success?: boolean } & DomAnalytics);
  if (data.success === false) return null;
  return data;
}

export async function getTape(symbol: string, limit: number = 200, minNotional?: number): Promise<{ symbol: string, entries: TapeEntry[] } | null> {
  let url = `${API_BASE}/api/flow/tape?symbol=${encodeURIComponent(symbol)}&limit=${limit}`;
  if (minNotional !== undefined) url += `&min_notional=${minNotional}`;
  const res = await fetch(url);
  const data = await safeJson<{ success?: boolean, symbol: string, entries: TapeEntry[] }>(res, { symbol, entries: [] });
  if (data.success === false) return null;
  return data;
}

export async function getHeatmap(symbol: string, windowSec?: number, tickGroup?: number): Promise<HeatmapSnapshot | null> {
  let url = `${API_BASE}/api/flow/heatmap?symbol=${encodeURIComponent(symbol)}`;
  if (windowSec !== undefined) url += `&window_sec=${windowSec}`;
  if (tickGroup !== undefined) url += `&tick_group=${tickGroup}`;
  const res = await fetch(url);
  const data = await safeJson<{ success?: boolean } & HeatmapSnapshot>(res, {} as { success?: boolean } & HeatmapSnapshot);
  if (data.success === false) return null;
  return data;
}

export async function getVolumeProfile(
  symbol: string, 
  mode: "SESSION" | "VISIBLE" | "FIXED_RANGE" = "SESSION",
  startTs?: number,
  endTs?: number,
  tickGroup?: number
): Promise<VolumeProfileSnapshot | null> {
  let url = `${API_BASE}/api/flow/volume-profile?symbol=${encodeURIComponent(symbol)}&mode=${mode}`;
  if (startTs !== undefined) url += `&start_ts=${startTs}`;
  if (endTs !== undefined) url += `&end_ts=${endTs}`;
  if (tickGroup !== undefined) url += `&tick_group=${tickGroup}`;
  const res = await fetch(url);
  const data = await safeJson<{ success?: boolean } & VolumeProfileSnapshot>(res, {} as { success?: boolean } & VolumeProfileSnapshot);
  if (data.success === false) return null;
  return data;
}

export async function getCVD(symbol: string, interval: string = "1m", limit: number = 240): Promise<{ symbol: string, points: CVDPoint[], vwap: number, bands: [number, number] } | null> {
  const res = await fetch(`${API_BASE}/api/flow/cvd?symbol=${encodeURIComponent(symbol)}&interval=${interval}&limit=${limit}`);
  const data = await safeJson<{ success?: boolean, symbol: string, points: CVDPoint[], vwap: number, bands: [number, number] }>(res, {} as { success?: boolean, symbol: string, points: CVDPoint[], vwap: number, bands: [number, number] });
  if (data.success === false) return null;
  return data;
}

export async function getMetrics(symbol: string): Promise<FlowMetrics | null> {
  const res = await fetch(`${API_BASE}/api/flow/metrics?symbol=${encodeURIComponent(symbol)}`);
  const data = await safeJson<{ success?: boolean } & FlowMetrics>(res, {} as { success?: boolean } & FlowMetrics);
  if (data.success === false) return null;
  return data;
}

export async function getSymbolInfo(symbol: string): Promise<Record<string, unknown> | null> {
  const res = await fetch(`${API_BASE}/api/flow/symbol-info?symbol=${encodeURIComponent(symbol)}`);
  const data = await safeJson<{ success?: boolean }>(res, { success: false });
  if (data.success === false) return null;
  return data;
}
