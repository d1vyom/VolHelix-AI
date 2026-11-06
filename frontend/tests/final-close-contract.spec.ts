import {test,expect} from '@playwright/test';
import {fixtures} from './fixtures';
import {mkdir} from 'node:fs/promises';
import {resolve} from 'node:path';
const holding={market:'spot',trade_id:'spot:SOLUSDT:42',id:'spot:SOLUSDT:42',symbol:'SOLUSDT',qty:.9999,side:'LONG',avg_entry_price:100,current_price:100,market_value:99.99,cost_basis:99.99,unrealized_pl:0,unrealized_plpc:0,stale:false,executed_qty:1,closed_qty:0,base_asset:'SOL',entry_fees:{SOL:.0001},exit_fees:{},fees_known:true,exit_fees_known:true};
for(const available of [0,123.45])test(`header uses normalized available balance ${available}`,async({page})=>{
  await fixtures(page);
  await page.route('**/api/market/account?**',route=>route.fulfill({json:{market:'spot',testnet:true,equity:1000,buying_power:available,balances:{},can_trade:true}}));
  await page.goto('/');
  await expect(page.getByText(`Testnet available: $${available.toFixed(2)} USDT`,{exact:true})).toBeVisible();
});
for(const state of ['FILLED','CANCELED'])test(`tracked close ${state} survives response loss reload and market switch with original ID`,async({page})=>{
  await fixtures(page);const sent:Record<string,unknown>[]=[];let reductions=0;let previews=0;const queries:string[]=[];
  await page.route('**/api/market/positions?**',route=>route.fulfill({json:{market:'spot',available:true,positions:[holding]}}));
  await page.route('**/api/exchange/close-position/preview',route=>{previews++;return route.fulfill({json:{approved:true,reason:'Approved',checks:{exchange_filters:true,inventory:true},quantity:'0.99',retained_quantity:'0.0099',price:'100',notional:'99'}});});
  await page.route('**/api/exchange/close-position',async route=>{
    sent.push(route.request().postDataJSON());reductions++;await route.abort();
  });
  await page.route('**/api/market/order-intents/**/reconcile?**',async route=>{
    queries.push(route.request().url());expect(route.request().postData()).toBeNull();
    await route.fulfill({json:{success:true,outcome:'ACKNOWLEDGED',status:state==='FILLED'?'CLOSED':'OPEN',exchange_status:state,executed_qty:state==='FILLED'?.99:.4,client_order_id:sent[0].client_order_id}});
  });
  await page.goto('/');await page.getByRole('button',{name:'Close Position',exact:true}).click();
  await page.getByRole('button',{name:'Preview testnet order'}).click();
  await expect(page.getByRole('dialog')).toContainText('Retained inventory');
  await expect(page.getByRole('dialog')).toContainText('.0099');expect(previews).toBe(1);
  if(state==='FILLED'){
    const folder=resolve('..','docs/artifacts/ui/final-repair');await mkdir(folder,{recursive:true});
    await page.getByRole('dialog').evaluate(dialog=>{const note=document.createElement('p');note.textContent='OFFLINE CONFIRMATION FIXTURE - NOT LIVE ACCOUNT PROOF';dialog.prepend(note);});
    await page.screenshot({path:resolve(folder,'tracked-close-preview.png'),fullPage:true,animations:'disabled'});
  }
  await page.getByRole('button',{name:'Confirm testnet order'}).click();
  await expect(page.getByRole('status').filter({hasText:'UNKNOWN: network response lost'})).toBeVisible();
  await page.getByRole('button',{name:'Futures',exact:true}).click();await page.reload();
  await page.getByRole('button',{name:'Reconcile / retry same intent'}).click();
  await expect.poll(()=>queries.length).toBe(1);
  expect(sent[0].client_order_id).toMatch(/^[A-Za-z0-9_-]{1,36}$/);
  expect(sent).toHaveLength(1);expect(sent[0]).toMatchObject({market:'spot',symbol:'SOLUSDT',trade_id:holding.trade_id});expect(reductions).toBe(1);
  expect(queries[0]).toContain(`/api/market/order-intents/${sent[0].client_order_id}/reconcile?market=spot`);
  await expect(page.getByRole('button',{name:'Reconcile / retry same intent'})).toHaveCount(0);
  expect(await page.evaluate(()=>sessionStorage.getItem('volhelix.pending-intent.v1'))).toBeNull();
});

for(const status of [404,502])test(`unknown close query ${status} never posts another close or clears identity`,async({page})=>{
  await fixtures(page);let closes=0;let queries=0;
  await page.addInitScript(holding=>sessionStorage.setItem('volhelix.pending-intent.v1',JSON.stringify({intent:{market:'spot',symbol:'SOLUSDT',side:'SELL',qty:.99,order_type:'MARKET',reduce_only:true,client_order_id:'original-close'},preview:{approved:true,checks:{},reason:'Approved'},close:holding})),holding);
  await page.route('**/api/exchange/close-position',route=>{closes++;return route.abort();});
  await page.route('**/api/market/order-intents/**/reconcile?**',route=>{queries++;return route.fulfill({status,json:{detail:status===404?'Intent not found':{outcome:'UNKNOWN',message:'Execution account identity mismatch'}}});});
  await page.goto('/');await page.getByRole('button',{name:'Reconcile / retry same intent'}).click();
  await expect.poll(()=>queries).toBe(1);expect(closes).toBe(0);
  await expect(page.getByRole('button',{name:'Reconcile / retry same intent'})).toBeEnabled();
  expect(await page.evaluate(()=>sessionStorage.getItem('volhelix.pending-intent.v1'))).toContain('original-close');
});
