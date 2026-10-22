import { test, expect, Page } from '@playwright/test';
import { mkdir } from 'node:fs/promises';
import { resolve } from 'node:path';

async function fixtures(page: Page) {
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

test('search supports keyboard selection, no matches and separate Futures catalog', async ({page}) => {
  await fixtures(page); await page.goto('/');
  const search = page.getByRole('combobox', {name:'Search markets'});
  await search.fill('ETH'); await expect(page.getByRole('option', {name:/ETHUSDT/})).toBeVisible();
  await search.press('ArrowDown'); await search.press('Enter');
  await expect(page.getByTestId('selected-market')).toContainText('ETHUSDT');
  await search.fill('NOTFOUND'); await expect(page.getByText('No matching markets')).toBeVisible();
  await page.getByRole('button', {name:'Futures',exact:true}).click();
  await search.fill('PEPE'); await expect(page.getByRole('option',{name:/1000PEPEUSDT/})).toBeVisible(); await search.press('ArrowDown'); await search.press('Enter');
  await expect(page.getByTestId('selected-market')).toContainText('futures');
  await expect(page.getByTestId('selected-market')).toContainText('1000PEPEUSDT');
});

test('catalog failure is visible and retry recovers', async ({page}) => {
  await fixtures(page);
  let fail=true;
  await page.route('**/api/market/instruments?**', async route => {
    if (fail) {fail=false; await route.fulfill({status:503,body:'unavailable'});}
    else await route.fallback();
  });
  await page.goto('/'); await page.getByRole('combobox', {name:'Search markets'}).focus();
  await expect(page.getByRole('button',{name:'Retry market search'})).toBeVisible();
  await page.getByRole('button',{name:'Retry market search'}).click();
  await expect(page.getByRole('option',{name:/ETHUSDT/})).toBeVisible();
});

test('preview shows risk verdict; no execution before confirmation; rejected order stays out of positions', async ({page}) => {
  const orders = await fixtures(page); await page.goto('/');
  await page.getByLabel('Order quantity').fill('0.001');
  await page.getByRole('button',{name:'Preview testnet order'}).click();
  await expect(page.getByRole('dialog')).toContainText('Approved by risk checks');
  expect(orders).toHaveLength(0);
  await page.getByRole('button',{name:'Confirm testnet order'}).click();
  await expect(page.getByRole('status').filter({hasText:'Exchange rejected test order'})).toBeVisible();
  expect(orders).toHaveLength(1); expect(orders[0].market).toBe('spot');
  expect(orders[0].client_order_id).toBeTruthy();
  await expect(page.getByText('No Active Positions', {exact:false})).toBeVisible();
});

test('failed risk check disables confirmation and Spot SELL routes tracked close', async ({page}) => {
  const orders=await fixtures(page);
  await page.route('**/api/market/order/preview', route => route.fulfill({contentType:'application/json',body:JSON.stringify({approved:false,reason:'Insufficient available balance',checks:{funds:false}})}));
  await page.goto('/'); await page.getByLabel('Order quantity').fill('0.001');
  await page.getByRole('button',{name:'Preview testnet order'}).click();
  await expect(page.getByRole('button',{name:'Confirm testnet order'})).toBeDisabled();
  await page.getByRole('button',{name:'Back to ticket'}).click();
  await page.getByLabel('Order side').selectOption('SELL');
  await expect(page.getByText('Spot SELL closes a tracked holding.')).toBeVisible();
  await expect(page.getByRole('button',{name:'Preview testnet order'})).toBeDisabled();
  expect(orders).toHaveLength(0);
});

test('uncertain submission retries with the same intent ID', async ({page}) => {
  await fixtures(page); const ids: string[]=[];
  await page.route('**/api/exchange/order', async route => {ids.push(route.request().postDataJSON().client_order_id); if(ids.length===1) await route.abort(); else await route.fulfill({contentType:'application/json',body:JSON.stringify({success:true,status:'UNKNOWN',client_order_id:ids[0]})});});
  await page.goto('/'); await page.getByLabel('Order quantity').fill('0.001');
  await page.getByRole('button',{name:'Preview testnet order'}).click(); await page.getByRole('button',{name:'Confirm testnet order'}).click();
  await page.getByRole('button',{name:'Reconcile / retry same intent'}).click();
  await expect.poll(() => ids.length).toBe(2); expect(ids[0]).toBe(ids[1]);
});

test('outage never displays invented funds or quotes', async ({page}) => {
  await page.route('**/api/**', route => route.fulfill({status:503,body:'unavailable'})); await page.goto('/');
  await expect(page.getByTestId('market-read-status')).toContainText('unavailable');
  await expect(page.getByText('$10,000.00')).toHaveCount(0);
  await expect(page.getByText('Binance Real Last')).toHaveCount(0);
  await expect(page.getByText('10/10 ARMED')).toHaveCount(0);
});

test('a delayed Spot quote cannot replace the selected Futures quote', async ({page}) => {
  await fixtures(page);
  let release: () => void = () => {};
  const gate = new Promise<void>(resolve => {release=resolve;});
  await page.route('**/api/market/quote?**', async route => {
    const url=new URL(route.request().url());
    if(url.searchParams.get('market')==='spot') {await gate; await route.fulfill({contentType:'application/json',body:JSON.stringify({market:'spot',symbol:'BTCUSDT',price:11111})}).catch(() => {});}
    else await route.fulfill({contentType:'application/json',body:JSON.stringify({market:'futures',symbol:'BTCUSDT',price:22222})});
  });
  await page.goto('/'); await page.getByRole('button',{name:'Futures',exact:true}).click();
  await expect(page.getByTestId('header-price')).toContainText('22,222'); release();
  await expect(page.getByTestId('header-price')).toContainText('22,222');
  await expect(page.getByTestId('header-price')).not.toContainText('11,111');
});

for(const width of [390,768,1440]) test(`selection and ticket controls fit ${width}px`,async ({page}) => {
  await page.setViewportSize({width,height:1000}); await fixtures(page); await page.goto('/');
  await expect(page.getByRole('combobox',{name:'Search markets'})).toBeVisible();
  await expect(page.getByRole('button',{name:'Preview testnet order'})).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
});

const holding={market:'spot',trade_id:'spot:ETHUSDT:42',id:'spot:ETHUSDT:42',symbol:'ETHUSDT',qty:0.2,side:'LONG',avg_entry_price:2200,current_price:null,market_value:null,cost_basis:440,unrealized_pl:null,unrealized_plpc:null,stale:true};

test('stale tracked positions remain visible and close the actual market symbol identity',async({page})=>{
  await fixtures(page); const closes:unknown[]=[];
  await page.route('**/api/market/positions?**',route=>route.fulfill({contentType:'application/json',body:JSON.stringify({market:'spot',available:false,error:'Account disconnected',positions:[holding]})}));
  await page.route('**/api/exchange/close-position',async route=>{closes.push(route.request().postDataJSON());await route.fulfill({contentType:'application/json',body:JSON.stringify({success:true,status:'FILLED',executed_qty:0.2})});});
  await page.goto('/');
  await expect(page.getByRole('status').filter({hasText:'STALE positions'})).toBeVisible();
  await page.getByRole('button',{name:'Close Position',exact:true}).click();
  await expect(page.getByRole('region',{name:'Tracked position close'})).toContainText('spot ETHUSDT');
  await page.getByRole('button',{name:'Preview testnet order'}).click();
  expect(closes).toHaveLength(0);
  await expect(page.getByRole('dialog')).toContainText('ETHUSDT');
  await page.getByRole('button',{name:'Confirm testnet order'}).click();
  await expect.poll(()=>closes).toEqual([{market:'spot',symbol:'ETHUSDT',trade_id:'spot:ETHUSDT:42'}]);
});

test('changing chart interval preserves tracked positions and failed sync stays unavailable',async({page})=>{
  await fixtures(page);let unavailable=false;
  await page.route('**/api/market/positions?**',async route=>{if(unavailable)await route.fulfill({status:503,body:'unavailable'});else await route.fulfill({contentType:'application/json',body:JSON.stringify({market:'spot',available:true,positions:[{...holding,stale:false}]})});});
  await page.goto('/');await expect(page.getByRole('button',{name:'Close Position',exact:true})).toBeVisible();
  await page.getByRole('button',{name:'5m',exact:true}).click();
  await expect(page.getByRole('button',{name:'Close Position',exact:true})).toBeVisible();
  unavailable=true;await page.getByRole('button',{name:'Sync Binance'}).click();
  await expect(page.getByRole('status').filter({hasText:/unavailable/i}).first()).toBeVisible();
  await expect(page.getByText('Binance account, positions & orders synchronized!')).toHaveCount(0);
  await expect(page.getByRole('button',{name:'Close Position',exact:true})).toBeVisible();
});

test('Futures disables Spot starts and scans while a running Spot bot can always be stopped',async({page})=>{
  await fixtures(page);let running=true;const mutations:string[]=[];
  await page.route('**/api/bot/auto-trading/**',async route=>{const path=new URL(route.request().url()).pathname;if(route.request().method()==='POST'){mutations.push(path);running=false;}await route.fulfill({contentType:'application/json',body:JSON.stringify(path.endsWith('/status')?{is_running:running,watched_symbols:['BTCUSDT'],total_automated_trades:0}:{success:true})});});
  await page.goto('/');await expect(page.getByRole('button',{name:'Pause Auto-Pilot'})).toBeEnabled();
  await page.getByRole('button',{name:'Futures',exact:true}).click();
  await expect(page.getByRole('button',{name:'Spot scanner only'})).toBeDisabled();
  await page.getByRole('button',{name:'Pause Auto-Pilot'}).click();
  await expect.poll(()=>mutations).toEqual(['/api/bot/auto-trading/stop']);
  await expect(page.getByRole('button',{name:'Enable Auto-Pilot'})).toBeDisabled();
  expect(mutations).toEqual(['/api/bot/auto-trading/stop']);
});

test('history follows shared market and preserves a visibly stale ledger on outage',async({page})=>{
  await fixtures(page);let unavailable=false;
  await page.route('**/api/trades?**',async route=>{
    const market=new URL(route.request().url()).searchParams.get('market');
    if(unavailable)await route.fulfill({status:503,body:'unavailable'});
    else await route.fulfill({contentType:'application/json',body:JSON.stringify([{trade_id:`${market}:TEST:1`,market,status:'CLOSED',symbol:market==='futures'?'FUTUREONLY':'SPOTONLY',proposal:{underlying:market==='futures'?'FUTUREONLY':'SPOTONLY',strategy_type:'MASTER_ORDER_FLOW'},qty:1,entry_price:2,exit_price:3,realized_pnl:1}])});
  });
  await page.goto('/history');await expect(page.getByText('SPOTONLY',{exact:false}).first()).toBeVisible();
  await page.getByRole('button',{name:'Futures',exact:true}).click();
  await expect(page.getByText('FUTUREONLY',{exact:false}).first()).toBeVisible();
  await expect(page.getByText('SPOTONLY',{exact:false})).toHaveCount(0);
  unavailable=true;await page.getByRole('button',{name:'Sync Ledger'}).click();
  await expect(page.getByRole('status').filter({hasText:/stale/i})).toBeVisible();
  await expect(page.getByText('FUTUREONLY',{exact:false}).first()).toBeVisible();
});

test('volatility has no invented quote or empirical analytics when unavailable',async({page})=>{
  await page.route('**/api/**',route=>route.fulfill({status:503,body:'unavailable'}));await page.goto('/volatility');
  await expect(page.getByText('Quote unavailable',{exact:false}).first()).toBeVisible();
  await expect(page.getByText('$76650.00',{exact:false})).toHaveCount(0);
  await expect(page.getByText('COMPLIANT',{exact:true})).toHaveCount(0);
  await expect(page.getByText('IV observations unavailable',{exact:false})).toBeVisible();
});

test('unknown bot status disables starts',async({page})=>{
  await fixtures(page);
  await page.route('**/api/bot/auto-trading/status',route=>route.fulfill({status:503,body:'unavailable'}));
  await page.goto('/');await expect(page.getByRole('button',{name:'Enable Auto-Pilot'})).toBeDisabled();
});

test('structured execution validation rejection remains readable',async({page})=>{
  await fixtures(page);
  await page.route('**/api/exchange/order',route=>route.fulfill({status:422,contentType:'application/json',body:JSON.stringify({detail:[{loc:['body','qty'],msg:'Invalid quantity',type:'value_error'}]})}));
  await page.goto('/');await page.getByLabel('Order quantity').fill('0.001');
  await page.getByRole('button',{name:'Preview testnet order'}).click();await page.getByRole('button',{name:'Confirm testnet order'}).click();
  await expect(page.getByRole('status').filter({hasText:'Order rejected'})).toBeVisible();
  await expect(page.getByRole('button',{name:'Preview testnet order'})).toBeEnabled();
});

test('history never invents missing execution values',async({page})=>{
  await fixtures(page);
  await page.route('**/api/trades/history?**',route=>route.fulfill({contentType:'application/json',body:JSON.stringify([{trade_id:'spot:LEGACY:4',market:'spot',status:'CLOSED',symbol:'LEGACY',current_price:123,proposal:{strategy_type:'MASTER_ORDER_FLOW'}}])}));
  await page.goto('/');
  await page.getByRole('button',{name:/History & Ledger/}).click();
  const row=page.getByRole('row').filter({hasText:'LEGACY'});
  for(const index of [4,5,6,7])await expect(row.locator('td').nth(index)).toContainText('—');
});

test('unknown intent survives reload and selection changes and reconciles its original payload',async({page})=>{
  await fixtures(page);const sent:Record<string,unknown>[]=[];
  await page.route('**/api/exchange/order',async route=>{sent.push(route.request().postDataJSON());await route.abort();});
  await page.goto('/');await page.getByLabel('Order quantity').fill('0.001');
  await page.getByRole('button',{name:'Preview testnet order'}).click();await page.getByRole('button',{name:'Confirm testnet order'}).click();
  await expect(page.getByRole('button',{name:'Reconcile / retry same intent'})).toBeVisible();
  await page.reload();await page.getByRole('button',{name:'Futures',exact:true}).click();
  await expect(page.getByRole('button',{name:'Preview testnet order'})).toBeDisabled();
  await page.getByRole('button',{name:'Reconcile / retry same intent'}).click();
  await expect.poll(()=>sent.length).toBe(2);expect(sent[1]).toEqual(sent[0]);expect(sent[1].market).toBe('spot');
});

test('mobile navigation keeps all workspace routes reachable',async({page})=>{
  await page.setViewportSize({width:390,height:1000});await fixtures(page);await page.goto('/');
  await page.getByText('Workspace navigation',{exact:true}).click();
  await page.getByRole('link',{name:'Order History',exact:true}).click();
  await expect(page).toHaveURL(/\/history$/);
});

for(const width of [390,768,1440])test(`five routes render without client errors at ${width}px`,async({page})=>{
  await fixtures(page);await page.setViewportSize({width,height:1000});
  const errors:string[]=[];page.on('pageerror',error=>errors.push(error.message));
  page.on('console',message=>{if(message.type()==='error'&&/hydrat|invalid.*child|unhandled/i.test(message.text()))errors.push(message.text());});
  const folder=resolve('..','.superpowers/sdd/2026-10-20-market-upgrade/task-7-screenshots');await mkdir(folder,{recursive:true});
  for(const route of ['/','/terminal','/history','/volatility','/audit']){
    await page.goto(route);await expect(page.getByRole('combobox',{name:'Search markets'})).toBeVisible();
    await expect(page.getByTestId('header-price')).toContainText('60,000');
    if(route==='/')await expect(page.getByRole('button',{name:'Preview testnet order'})).toBeVisible();
    if(route==='/terminal')await expect(page.getByText('Waiting for footprint...')).toBeVisible();
    await page.screenshot({path:resolve(folder,`${route==='/'?'dashboard':route.slice(1)}-${width}.png`),fullPage:true,caret:'initial',animations:'disabled'});
  }
  expect(errors).toEqual([]);
});
