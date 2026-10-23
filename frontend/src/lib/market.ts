import type { ExchangeAccount, ExchangeBar, ExchangeOrder, ExchangePosition } from './api';
export type Market = 'spot' | 'futures';
export interface Instrument { market: Market; symbol: string; base_asset: string; quote_asset: string; contract_type?: string }
export interface MarketQuote { market: Market; symbol: string; price: number; timestamp?: string }
export interface Depth { market: Market; symbol: string; bids: [number, number][]; asks: [number, number][] }
export interface PositionSnapshot { market: Market; available: boolean; error?: string; positions: ExchangePosition[] }
export interface OrderIntent { market: Market; symbol: string; qty: number; side: 'BUY'|'SELL'; order_type: 'MARKET'|'LIMIT'; limit_price?: number; client_order_id: string; reduce_only?: boolean }
export interface Preview { approved: boolean; reason: string; checks: Record<string, boolean>; market?: Market; quantity?: string; price?: string; notional?: string; risk_coverage?: string; coverage_started_at?: string; testnet?: boolean }
const base = process.env.NEXT_PUBLIC_API_URL || '';
interface ExecutionReply {
  success?:boolean; outcome?:string; status?:string; exchange_status?:string; executed_qty?:number;
  error?:string; detail?:string|{outcome?:string;message?:string}|unknown[];
}
export async function readExecutionResponse(response:Response) {
  const result=await response.json() as ExecutionReply;
  const detail=result.detail && typeof result.detail==='object' && !Array.isArray(result.detail)?result.detail:null;
  const outcome=detail?.outcome || result.outcome;
  const state=String(result.exchange_status || result.status || '').toUpperCase();
  const rejected=['REJECTED','NOT_DISPATCHED'].includes(outcome || '') || (response.ok&&state==='REJECTED');
  const acknowledged=response.ok&&result.success===true&&(outcome==='ACKNOWLEDGED'||['NEW','PARTIALLY_FILLED','FILLED','PENDING_NEW','CANCELED','EXPIRED','EXPIRED_IN_MATCH','CLOSED','OPEN'].includes(state));
  // FastAPI schema validation happens before the order handler can dispatch.
  const invalidInput=response.status===422&&Array.isArray(result.detail);
  const uncertain=outcome==='UNKNOWN'||outcome==='DISPATCHING'||state==='UNKNOWN'||state==='DISPATCHING'||(!rejected&&!acknowledged&&!invalidInput);
  const error=result.error || detail?.message || (typeof result.detail==='string'?result.detail:`Order rejected (HTTP ${response.status})`);
  return {...result,success:response.ok&&result.success===true,uncertain,error,state};
}
export async function reconcileOrderIntent(market:Market,clientOrderId:string) {
  try {
    return await readExecutionResponse(await fetch(`${base}/api/market/order-intents/${encodeURIComponent(clientOrderId)}/reconcile?market=${market}`,{method:'POST'}));
  }catch{return {success:false,uncertain:true,error:'UNKNOWN: exchange reconciliation unavailable; reservation retained'};}
}
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
export function formatMoney(value: number | null | undefined) {
  if (value == null || !Number.isFinite(value)) return '—';
  return value !== 0 && Math.abs(value) < 1
    ? value.toLocaleString('en-US', { maximumSignificantDigits: 8 })
    : value.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

// Instrument reads currently omit tick metadata; retain all representable price digits.
const priceFormat = new Intl.NumberFormat('en-US', { maximumSignificantDigits: 17 });
export function formatPrice(value: number | null | undefined) {
  return value != null && Number.isFinite(value) ? priceFormat.format(value) : '—';
}
