'use client';
import { useEffect, useRef, useState } from 'react';
import type { ExchangePosition } from '@/lib/api';
import { OrderIntent, Preview, request, readExecutionResponse } from '@/lib/market';
import { useMarket } from './MarketProvider';

type Attempt = { intent: OrderIntent; preview: Preview; close?: ExchangePosition };
const storageKey='volhelix.pending-intent.v1';
export function OrderTicket({onUpdated,close,onDismiss}:{onUpdated?:()=>void;close?:ExchangePosition;onDismiss?:()=>void}) {
  const {market,symbol}=useMarket();
  const [side,setSide]=useState<'BUY'|'SELL'>('BUY'); const [orderType,setOrderType]=useState<'MARKET'|'LIMIT'>('MARKET');
  const [qty,setQty]=useState(''); const [price,setPrice]=useState(''); const [attempt,setAttempt]=useState<Attempt|null>(null);
  const [busy,setBusy]=useState(false); const [notice,setNotice]=useState(''); const [unknown,setUnknown]=useState(false);
  const dialog=useRef<HTMLDialogElement>(null); const alive=useRef(true);
  const previewButton=useRef<HTMLButtonElement>(null);
  useEffect(()=>{alive.current=true;return ()=>{alive.current=false;};},[]);
  useEffect(()=>{
    const timer=setTimeout(()=>{
    try {const saved=JSON.parse(sessionStorage.getItem(storageKey)||'null') as Attempt|null;if(saved){setAttempt(saved);setUnknown(true);setNotice(`UNKNOWN: unresolved ${saved.intent.market} ${saved.intent.symbol} intent. Reconcile before starting another.`);}}catch{sessionStorage.removeItem(storageKey);}
    },0);return ()=>clearTimeout(timer);
  },[]);
  useEffect(()=>{
    const stage=(event:Event)=>{const data=(event as CustomEvent<{market:string;symbol:string;price:number}>).detail;if(data.market===market&&data.symbol===symbol&&!unknown){setOrderType('LIMIT');setPrice(String(data.price));setNotice('DOM price staged. Review quantity, preview and confirm.');}};
    window.addEventListener('volhelix:stage-order',stage);return ()=>window.removeEventListener('volhelix:stage-order',stage);
  },[market,symbol,unknown]);
  const targetMarket=close?.market || market; const targetSymbol=close?.symbol || symbol;
  async function preview(event:React.FormEvent) {
    event.preventDefault();setBusy(true);setNotice('');
    const intent:OrderIntent={market:targetMarket,symbol:targetSymbol,qty:close?close.qty:Number(qty),side:close?(close.side==='SHORT'?'BUY':'SELL'):side,order_type:close?'MARKET':orderType,client_order_id:crypto.randomUUID().replaceAll('-',''),...(close?{reduce_only:true}:{}),...(!close&&orderType==='LIMIT'?{limit_price:Number(price)}:{})};
    try {const verdict=await request<Preview>('/api/market/order/preview',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(intent)});if(!alive.current)return;setAttempt({intent,preview:verdict,close});dialog.current?.showModal();}
    catch(error){if(alive.current)setNotice(error instanceof Error?error.message:'Preview unavailable');}
    finally{if(alive.current)setBusy(false);}
  }
  async function submit() {
    if(!attempt || !attempt.preview.approved || busy)return;
    setBusy(true);setUnknown(false);sessionStorage.setItem(storageKey,JSON.stringify(attempt));
    try {
      const response=await fetch(`${process.env.NEXT_PUBLIC_API_URL||''}${attempt.close?'/api/exchange/close-position':'/api/exchange/order'}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(attempt.close?{market:attempt.intent.market,symbol:attempt.intent.symbol,trade_id:attempt.close.trade_id || attempt.close.id}:attempt.intent)});
      const result=await readExecutionResponse(response);
      const {state,uncertain}=result;
      if(!uncertain)sessionStorage.removeItem(storageKey);
      if(!alive.current)return;
      setUnknown(uncertain);
      setNotice(uncertain?`UNKNOWN: outcome unconfirmed for ${attempt.intent.symbol}. Reconcile using the same intent.`:result.success?`${attempt.intent.market} ${attempt.intent.symbol}: ${state || 'Acknowledged'}${result.executed_qty!=null?` · Executed ${result.executed_qty}`:''}`:result.error);
      dialog.current?.close();if(!uncertain)setAttempt(null);onUpdated?.();
    }catch{if(alive.current){setUnknown(true);setNotice('UNKNOWN: network response lost. Reconcile using the same intent.');dialog.current?.close();}}
    finally{if(alive.current)setBusy(false);}
  }
  const spotSell=!close&&market==='spot'&&side==='SELL';
  return <section className="trade-ticket" aria-label={close?'Tracked position close':'Testnet order ticket'}>
    <h2 className="font-bold text-sm">{close?'Close tracked position':'Order ticket'} · <span className="text-[#f7a600]">{targetMarket} {targetSymbol}</span></h2>
    <p className="text-[#878996] text-xs">Testnet execution · Production market data</p>
    <form onSubmit={preview} className="space-y-3">
      {close?<p>Close {close.qty} {close.symbol} · {close.side} · {close.trade_id || close.id}</p>:<>
        <label>Order side<select aria-label="Order side" value={side} disabled={unknown||busy} onChange={e=>setSide(e.target.value as typeof side)}><option value="BUY">Buy / Long</option><option value="SELL">{market==='spot'?'Sell tracked holding':'Sell / Short'}</option></select></label>
        {spotSell&&<p role="note">Spot SELL closes a tracked holding. Use Close Position in the positions table to select its actual identity.</p>}
        <label>Order type<select aria-label="Order type" value={orderType} disabled={unknown||busy} onChange={e=>setOrderType(e.target.value as typeof orderType)}><option value="MARKET">Market</option><option value="LIMIT">Limit</option></select></label>
        <label>Order quantity<input aria-label="Order quantity" type="number" min="0.000000000001" step="any" required value={qty} disabled={unknown||busy} onChange={e=>setQty(e.target.value)} /></label>
        {orderType==='LIMIT'&&<label>Limit price<input aria-label="Limit price" type="number" min="0.000000000001" step="any" required value={price} disabled={unknown||busy} onChange={e=>setPrice(e.target.value)} /></label>}
      </>}
      <button ref={previewButton} className="gold-button" disabled={busy||unknown||spotSell} type="submit">{busy?'Checking…':'Preview testnet order'}</button>
      {onDismiss&&<button type="button" onClick={onDismiss}>Back to positions</button>}
    </form>
    {notice&&<p role="status" className="break-words text-[#f7a600]">{notice}</p>}
    {unknown&&<button type="button" className="gold-button" disabled={busy} onClick={submit}>Reconcile / retry same intent</button>}
    <dialog ref={dialog} onClose={()=>previewButton.current?.focus()} onKeyDown={event=>{
      if(event.key!=='Tab')return;
      const controls=Array.from(event.currentTarget.querySelectorAll<HTMLButtonElement>('button:not(:disabled)'));
      const first=controls[0],last=controls.at(-1);
      if(event.shiftKey&&document.activeElement===first){event.preventDefault();last?.focus();}
      else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first?.focus();}
    }} onCancel={event=>{if(busy)event.preventDefault();}} className="confirmation-dialog" aria-label="Confirm testnet order">
      {attempt&&<><h2 className="font-bold text-lg">Review {attempt.close?'position close':'testnet order'}</h2>
        <p>{attempt.intent.market} · {attempt.intent.symbol} · {attempt.intent.side} · {attempt.intent.order_type}</p>
        <dl><dt>Quantity</dt><dd>{attempt.preview.quantity || attempt.intent.qty}</dd><dt>Preview price</dt><dd>{attempt.preview.price || 'Unavailable'}</dd><dt>Notional</dt><dd>{attempt.preview.notional || 'Unavailable'}</dd><dt>Client intent ID</dt><dd className="break-all">{attempt.intent.client_order_id}</dd></dl>
        <strong className={attempt.preview.approved?'text-[#20b26c]':'text-[#ef454a]'}>{attempt.preview.approved?'Risk approved':'Risk rejected'}: {attempt.preview.reason}</strong>
        <ul>{Object.entries(attempt.preview.checks).map(([name,passed])=><li key={name}>{passed?'PASS':'FAIL'} · {name}</li>)}</ul>
        <p>Risk coverage: {attempt.preview.risk_coverage || 'See server checks'}{attempt.preview.coverage_started_at?` since ${attempt.preview.coverage_started_at}`:''}</p>
        <p>Server rechecks at execution. Market execution price can change. Testnet only.</p>
        <div className="flex gap-3"><button type="button" disabled={busy} onClick={()=>{dialog.current?.close();setAttempt(null);}}>Back to ticket</button><button type="button" className="gold-button" disabled={!attempt.preview.approved||busy} onClick={submit}>Confirm testnet order</button></div>
      </>}
    </dialog>
  </section>;
}
