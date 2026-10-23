import { test, expect } from '@playwright/test';
import { fixtures, captureFixture } from './fixtures';
import { mkdir, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';

const feeTrade={trade_id:'spot:SOLUSDT:fee-case',market:'spot',status:'CLOSED',symbol:'SOLUSDT',proposal:{underlying:'SOLUSDT',strategy_type:'MASTER_ORDER_FLOW'},entry_price:100,exit_price:100.01,realized_pnl:0.01,net_realized_pnl:null,pnl_basis:'gross_price_difference_fees_separate',entry_fees:{BNB:0.02},exit_fees:{USDT:0.03},fees_known:true,exit_fees_known:true,dust_qty:0};

test('gross gain with larger fees never claims positive net profit and native fees remain visible',async({page})=>{
  await page.setViewportSize({width:1440,height:1000});
  await fixtures(page);
  await page.route(/\/api\/trades(?:\/history)?\?/,route=>route.fulfill({json:[feeTrade,{...feeTrade,trade_id:'spot:SOLUSDT:dust',status:'OPEN',realized_pnl:null,exit_price:null,dust_qty:0.00001,dust_reason:'Below minimum quantity',exit_fees_known:false}]}));
  await page.goto('/');await page.getByRole('button',{name:/History & Ledger/}).click();
  await expect(page.getByText('Realized gross P&L',{exact:true})).toBeVisible();
  await expect(page.getByText('Realized Net P&L',{exact:true})).toHaveCount(0);
  await expect(page.getByText('Fees excluded · Net P&L unavailable',{exact:false}).first()).toBeVisible();
  await expect(page.getByText('0.02 BNB',{exact:false}).first()).toBeVisible();
  await expect(page.getByText('0.03 USDT',{exact:false}).first()).toBeVisible();
  await page.goto('/history');
  await expect(page.getByText('0.02 BNB',{exact:false}).first()).toBeVisible();
  await expect(page.getByText('Dust: 0.00001',{exact:false})).toBeVisible();
  await captureFixture(page,'history-native-fees-1440');
});

test('unknown ledger PnL and incomplete fee coverage remain unavailable',async({page})=>{
  await fixtures(page);
  await page.route(/\/api\/trades(?:\/history)?\?/,route=>route.fulfill({json:[{...feeTrade,realized_pnl:null,entry_fees:{},fees_known:null,exit_fees_known:false}]}));
  await page.goto('/history');
  await expect(page.getByText('Gross P&L unavailable',{exact:false})).toBeVisible();
  await expect(page.getByText('Fee coverage incomplete / unknown',{exact:false})).toBeVisible();
  await expect(page.getByText('SYSTEM WIN RATE',{exact:true}).first().locator('..')).toContainText('\u2014');
});

test('subcent market prices stay nonzero across market summary and order book',async({page})=>{
  await fixtures(page);
  await page.route('**/api/market/quote?**',route=>route.fulfill({json:{market:'spot',symbol:'BTCUSDT',price:0.00000123}}));
  await page.route('**/api/market/depth?**',route=>route.fulfill({json:{market:'spot',symbol:'BTCUSDT',bids:[[0.00000122,1]],asks:[[0.00000124,2]]}}));
  await page.goto('/');
  await expect(page.getByTestId('header-price')).toContainText('0.00000123');
  await expect(page.getByText('0.00000122',{exact:false}).first()).toBeVisible();
});

test('unknown flow analytics use unavailable states and session profile has no dead modes',async({page})=>{
  await fixtures(page);await page.goto('/terminal');
  await expect(page.getByText('Waiting for footprint...')).toBeVisible();
  await expect(page.getByText('NONE',{exact:true})).toHaveCount(0);
  await expect(page.getByText('RATE: —/s',{exact:false})).toBeVisible();
  await page.getByRole('combobox',{name:'Workspace layout'}).selectOption('ANALYSIS');
  await expect(page.getByText('Session profile',{exact:true})).toBeVisible();
  await expect(page.getByText('VISIBLE',{exact:true})).toHaveCount(0);
  await page.getByRole('combobox',{name:'Workspace layout'}).selectOption('LIQUIDITY');
  await expect(page.getByText('Waiting for heatmap...')).toBeVisible();
  await expect(page.getByText('Waiting for DOM...')).toBeVisible();
  await expect(page.getByText('Session profile',{exact:true})).toBeVisible();
  await captureFixture(page,'terminal-liquidity-1280');
});

test('confirmation traps keyboard focus, Escape returns focus to ticket without submitting',async({page})=>{
  const orders=await fixtures(page);await page.setViewportSize({width:390,height:900});await page.goto('/');
  await page.getByLabel('Order quantity').fill('0.001');const preview=page.getByRole('button',{name:'Preview testnet order'});await preview.click();
  const dialog=page.getByRole('dialog');await expect(dialog).toBeVisible();
  await captureFixture(page,'confirmation-390');
  for(let i=0;i<6;i++){await page.keyboard.press('Tab');expect(await dialog.evaluate(el=>el.contains(document.activeElement))).toBe(true);}
  await page.keyboard.press('Escape');await expect(dialog).not.toBeVisible();await expect(preview).toBeFocused();expect(orders).toHaveLength(0);
});

for(const width of [390,768,1440])test(`capture all five routes and inspect layout at ${width}px`,async({page})=>{
  await fixtures(page);await page.setViewportSize({width,height:1000});await page.emulateMedia({reducedMotion:'reduce'});
  const baseline=process.env.UI_BASELINE==='1';const folder=resolve('..',baseline?'tmp/task8b-baseline':'docs/artifacts/ui/task-8b');await mkdir(folder,{recursive:true});
  const errors:string[]=[];const consoleErrors:string[]=[];const mutations:string[]=[];page.on('pageerror',e=>errors.push(e.message));
  page.on('console',message=>{if(message.type()==='error')consoleErrors.push(message.text());});
  page.on('request',req=>{if(req.method()==='POST'&&req.url().includes('/api/'))mutations.push(req.url());});
  const observations=[];
  for(const route of ['/','/terminal','/volatility','/audit','/history']){
    await page.goto(route);await expect(page.getByTestId('header-price')).toContainText('60,000');
    if(route==='/terminal'){
      await expect(page.getByText('Waiting for footprint...')).toBeVisible();
      await expect(page.getByText('Waiting for bar data...')).toBeVisible();
      await expect(page.getByText('Waiting for DOM...')).toBeVisible();
      await expect(page.getByText('Waiting for trades...')).toBeVisible();
    }
    if(route==='/volatility')await expect(page.locator('.js-plotly-plot')).toBeVisible({timeout:20000});
    await page.evaluate(()=>document.fonts.ready);
    await page.evaluate(()=>{const note=document.createElement('div');note.textContent='OFFLINE UI FIXTURE · NOT LIVE MARKET / ACCOUNT PROOF';note.style.cssText='position:relative;flex-shrink:0;background:#252119;color:#ffd27a;padding:5px;text-align:center;font:10px sans-serif;';document.body.prepend(note);});
    observations.push({route,...await page.evaluate(()=>({font:getComputedStyle(document.body).fontFamily,scrollWidth:document.documentElement.scrollWidth,width:innerWidth}))});
    if(!baseline)expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
    await page.screenshot({path:resolve(folder,`${route==='/'?'dashboard':route.slice(1)}-${width}.png`),fullPage:true,animations:'disabled'});
  }
  await writeFile(resolve(folder,`observations-${width}.json`),JSON.stringify({observations,errors,consoleErrors,mutations},null,2));
  expect(errors).toEqual([]);expect(mutations).toEqual([]);
});
test('audit distinguishes a read failure from an empty successful trail and retry recovers',async({page})=>{
  await fixtures(page);let fail=true;
  await page.route('**/api/audit',route=>fail?route.fulfill({status:503,body:'unavailable'}):route.fulfill({json:[]}));
  await page.goto('/audit');await expect(page.getByRole('status').filter({hasText:'Audit unavailable'})).toBeVisible();
  await expect(page.getByText('No audit records yet.',{exact:false})).toHaveCount(0);
  fail=false;await page.getByRole('button',{name:'Retry audit'}).click();
  await expect(page.getByText('No audit records yet.',{exact:false})).toBeVisible();
});
test('illustrative volatility model keeps a subcent source quote and positive strike range',async({page})=>{
  await fixtures(page);await page.route('**/api/market/quote?**',route=>route.fulfill({json:{market:'spot',symbol:'BTCUSDT',price:0.00000123}}));
  await page.goto('/volatility');
  await expect(page.getByText('Production spot quote:',{exact:false})).toContainText('0.00000123');
  const plot=page.locator('.js-plotly-plot');await expect(plot).toBeVisible({timeout:20000});
  const strikes=await plot.evaluate(el=>(el as HTMLElement & {data:{y:number[]}[]}).data[0].y);
  expect(strikes.every(p=>p>0)).toBe(true);expect(Math.max(...strikes)).toBeLessThan(0.000002);
});
