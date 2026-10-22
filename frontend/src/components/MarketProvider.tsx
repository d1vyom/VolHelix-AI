'use client';
import { createContext, useContext, useEffect, useState } from 'react';
import { Depth, Market, MarketQuote, marketPath, readAccount, request } from '@/lib/market';
import type { ExchangeAccount } from '@/lib/api';

function useMarketState() {
  const [selection,setSelection] = useState<{market:Market;symbol:string}>({market:'spot',symbol:'BTCUSDT'});
  const [data,setData] = useState<{key:string;quote:MarketQuote|null;account:ExchangeAccount|null;depth:Depth|null;error:string;updated:number}>({key:'',quote:null,account:null,depth:null,error:'Loading market data',updated:0});
  const [retry,setRetry] = useState(0);
  const key=`${selection.market}:${selection.symbol}`;
  useEffect(()=>{
    const controller=new AbortController(); let alive=true;
    async function refresh() {
      const results=await Promise.allSettled([
        request<MarketQuote>(marketPath('quote',selection.market,selection.symbol),{signal:controller.signal}),
        readAccount(selection.market,controller.signal),
        request<Depth>(marketPath('depth',selection.market,selection.symbol),{signal:controller.signal}),
      ]);
      if(!alive) return;
      const [quote,account,depth]=results;
      setData({key,quote:quote.status==='fulfilled' && quote.value.price>0 ? quote.value : null,account:account.status==='fulfilled'?account.value:null,depth:depth.status==='fulfilled'?depth.value:null,error:results.some(r=>r.status==='rejected') ? results.filter(r=>r.status==='rejected').map(r=>r.reason.message).join('; ') : '',updated:Date.now()});
    }
    void refresh(); const timer=setInterval(refresh,5000);
    return ()=>{alive=false;controller.abort();clearInterval(timer);};
  },[selection,key,retry]);
  const current=data.key===key ? data : {quote:null,account:null,depth:null,error:'Loading market data',updated:0};
  return {...selection,...current,select:(market:Market,symbol=selection.symbol)=>setSelection(previous=>previous.market===market&&previous.symbol===symbol?previous:{market,symbol}),refresh:()=>setRetry(n=>n+1)};
}
type MarketContextValue = ReturnType<typeof useMarketState>;
const Context=createContext<MarketContextValue|null>(null);
export function MarketProvider({children}:{children:React.ReactNode}) { const state=useMarketState(); return <Context.Provider value={state}>{children}</Context.Provider>; }
export function useMarket() { const state=useContext(Context); if(!state) throw new Error('MarketProvider required'); return state; }
