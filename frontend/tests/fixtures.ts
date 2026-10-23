import type { Page } from '@playwright/test';
import { mkdir } from 'node:fs/promises';
import { resolve } from 'node:path';

export async function captureFixture(page: Page, name: string) {
  const folder=resolve('..','docs/artifacts/ui/task-8b');
  await mkdir(folder,{recursive:true});
  await page.evaluate(()=>{
    const note=document.createElement('div');
    note.textContent='OFFLINE UI FIXTURE · NOT LIVE MARKET / ACCOUNT PROOF';
    note.style.cssText='position:relative;flex-shrink:0;background:#252119;color:#ffd27a;padding:5px;text-align:center;font:10px sans-serif;';
    document.body.prepend(note);
  });
  await page.screenshot({path:resolve(folder,`${name}.png`),fullPage:true,animations:'disabled'});
}

export async function fixtures(page: Page) {
  const orders: Record<string, unknown>[] = [];
  await page.route('**/api/**', async route => {
    const url = new URL(route.request().url());
    const symbol = url.searchParams.get('symbol') || 'BTCUSDT';
    const market = url.searchParams.get('market') || 'spot';
    let body: unknown = [];
    if (url.pathname === '/api/market/instruments') {
      const search = url.searchParams.get('search') || '';
      body = {market, instruments: ['BTCUSDT','ETHUSDT','1000PEPEUSDT'].filter(s => s.includes(search.toUpperCase())).map(symbol => ({market,symbol,base_asset:symbol.replace('USDT',''),quote_asset:'USDT'}))};
    } else if (url.pathname === '/api/market/account') body = {market,testnet:true,equity:0,cash:0,buying_power:0,portfolio_value:0,status:'ACTIVE',currency:'USDT'};
    else if (url.pathname === '/api/market/positions') body = {market, available:true, positions:[]};
    else if (url.pathname === '/api/market/quote') body = {market,symbol,price:symbol === 'ETHUSDT' ? 2200 : 60000};
    else if (url.pathname === '/api/market/depth') body = {market,symbol,bids:[[59999,1]],asks:[[60001,2]]};
    else if (url.pathname === '/api/market/bars') body = {market,symbol,bars:[]};
    else if (url.pathname === '/api/market/order/preview') body = {...route.request().postDataJSON(),approved:true,reason:'Approved by risk checks',checks:{funds:true,allocation:true},quantity:'0.001',price:'60000',notional:'60',testnet:true,risk_coverage:'observed testnet equity'};
    else if (url.pathname === '/api/exchange/order') { orders.push(route.request().postDataJSON()); body={success:false,error:'Exchange rejected test order',status:'REJECTED'}; }
    else if (url.pathname.includes('auto-trading/status')) body = {is_running:false,guardian_active:false,watched_symbols:[],scanner_diagnostics:{},total_automated_trades:0};
    else if (url.pathname.includes('/flow/')) body = {success:false,error:'Waiting for stream'};
    await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(body)});
  });
  return orders;
}
