'use client';
import { useEffect, useId, useState } from 'react';
import { Instrument, request } from '@/lib/market';
import { useMarket } from './MarketProvider';
export function MarketSelector() {
  const {market,symbol,select}=useMarket(); const id=useId();
  const [search,setSearch]=useState(''); const [open,setOpen]=useState(false); const [active,setActive]=useState(-1);
  const [result,setResult]=useState<{key:string;items:Instrument[];error:string}>({key:'',items:[],error:''}); const [retry,setRetry]=useState(0);
  const key=`${market}:${search}`;
  useEffect(()=>{
    const controller=new AbortController(); let alive=true;
    const timer=setTimeout(()=>{
      request<{instruments:Instrument[]}>(`/api/market/instruments?${new URLSearchParams({market,search})}`,{signal:controller.signal})
        .then(data=>{if(alive)setResult({key,items:data.instruments,error:''});})
        .catch(error=>{if(alive)setResult({key,items:[],error:error.message});});
    },150);
    return ()=>{alive=false;clearTimeout(timer);controller.abort();};
  },[market,search,key,retry]);
  const current=result.key===key?result:null; const items=current?.items || [];
  const choose=(item:Instrument)=>{select(item.market,item.symbol);setOpen(false);setSearch('');setActive(-1);};
  return <div className="market-selector">
    <div className="flex gap-1" aria-label="Market type">{(['spot','futures'] as const).map(mode=><button key={mode} type="button" aria-pressed={market===mode} className={market===mode?'market-active':'market-muted'} onClick={()=>{select(mode,'BTCUSDT');setSearch('');setActive(-1);}}>{mode==='spot'?'Spot':'Futures'}</button>)}</div>
    <div className="relative min-w-0 flex-1">
      <input role="combobox" aria-label="Search markets" aria-expanded={open} aria-controls={id} aria-autocomplete="list" aria-activedescendant={active>=0?`${id}-${active}`:undefined} value={search} placeholder={`${symbol} · Search markets`} onFocus={()=>setOpen(true)} onBlur={()=>setOpen(false)} onChange={event=>{setSearch(event.target.value);setOpen(true);setActive(-1);}} onKeyDown={event=>{
        if(event.key==='ArrowDown'){event.preventDefault();setOpen(true);setActive(i=>Math.min(i+1,items.length-1));}
        if(event.key==='ArrowUp'){event.preventDefault();setActive(i=>Math.max(0,i-1));}
        if(event.key==='Enter'&&open&&items.length){event.preventDefault();choose(items[Math.max(0,active)]);}
        if(event.key==='Escape')setOpen(false);
      }} />
      {open&&<div className="market-options" id={id} role="listbox" aria-label="Matching markets">
        {!current?<p>Searching markets…</p>:current.error?<div role="alert"><p>Market search unavailable</p><button onMouseDown={e=>e.preventDefault()} onClick={()=>setRetry(n=>n+1)} aria-label="Retry market search">Retry</button></div>:items.length===0?<p>No matching markets</p>:items.slice(0,100).map((item,index)=><button role="option" aria-selected={active===index || symbol===item.symbol} id={`${id}-${index}`} key={item.symbol} onMouseDown={e=>e.preventDefault()} onClick={()=>choose(item)}><strong>{item.symbol}</strong><span>{item.base_asset} / {item.quote_asset} · {market}</span></button>)}
      </div>}
    </div>
  </div>;
}
