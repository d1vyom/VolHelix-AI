import type { ExchangeAccount, ExchangeBar, ExchangeOrder, ExchangePosition } from './api';
export type Market = 'spot' | 'futures';
export interface Instrument { market: Market; symbol: string; base_asset: string; quote_asset: string; contract_type?: string }
export interface MarketQuote { market: Market; symbol: string; price: number; timestamp?: string }
export interface Depth { market: Market; symbol: string; bids: [number, number][]; asks: [number, number][] }
export interface PositionSnapshot { market: Market; available: boolean; error?: string; positions: ExchangePosition[] }
export interface OrderIntent { market: Market; symbol: string; qty: number; side: 'BUY'|'SELL'; order_type: 'MARKET'|'LIMIT'; limit_price?: number; client_order_id: string; reduce_only?: boolean }
export interface Preview { approved: boolean; reason: string; checks: Record<string, boolean>; market?: Market; quantity?: string; price?: string; notional?: string; risk_coverage?: string; coverage_started_at?: string; testnet?: boolean }
const base = process.env.NEXT_PUBLIC_API_URL || '';
export async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${base}${path}`, { ...init, cache: 'no-store' });
  const data = await response.json().catch(() => null);
  // A stale position snapshot intentionally includes both saved exposure and an error.
  if (!response.ok || !data || (data.error && data.available !== false) || data.success === false) {
    const detail = data?.detail || data?.error;
    throw new Error(typeof detail === 'string' ? detail : `Data unavailable (HTTP ${response.status})`);
  }
  return data as T;
}
export const marketPath = (path: string, market: Market, symbol?: string) => `/api/market/${path}?${new URLSearchParams({market,...(symbol ? {symbol} : {})})}`;
export const readAccount = (market: Market, signal?: AbortSignal) => request<ExchangeAccount>(marketPath('account',market),{signal});
export const readPositions = (market: Market, signal?: AbortSignal) => request<PositionSnapshot>(marketPath('positions',market),{signal});
export const readOrders = (market: Market, signal?: AbortSignal) => request<ExchangeOrder[]>(`/api/exchange/orders?market=${market}`,{signal});
export async function readBars(market: Market, symbol: string, interval: string, signal?: AbortSignal): Promise<ExchangeBar[]> {
  const result=await request<{bars: (ExchangeBar & {open_time?: number})[]}>(`${marketPath('bars',market,symbol)}&interval=${interval.toLowerCase()}`,{signal});
  return result.bars.map(bar=>({...bar,time:bar.time || new Date(bar.open_time!).toISOString()}));
}
export function formatMoney(value: number | null | undefined) { return value != null && Number.isFinite(value) ? value.toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2}) : '—'; }
