'use client';
import { formatPrice } from '@/lib/market';
import { useMarket } from './MarketProvider';
export function MarketDepth(){
  const {depth,market,symbol}=useMarket();
  return <section className="trade-ticket" aria-label="Production order book"><h2 className="font-bold">Order book · {market} {symbol}</h2>{!depth||(!depth.bids.length&&!depth.asks.length)?<p>Depth unavailable</p>:<div className="grid grid-cols-2 gap-4 text-xs font-mono">{(['bids','asks'] as const).map(side=><div key={side}><strong className={side==='bids'?'text-[#20b26c]':'text-[#ef454a]'}>{side==='bids'?'Bids':'Asks'}</strong>{depth[side].slice(0,8).map(([price,size])=><div key={price} className="flex justify-between gap-2"><span>{formatPrice(price)}</span><span>{size}</span></div>)}</div>)}</div>}</section>;
}
