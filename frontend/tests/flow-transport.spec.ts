import { test, expect } from '@playwright/test';
import { createServer, Server as HttpServer } from 'node:http';
import { Server } from 'socket.io';
import { fixtures, captureFixture } from './fixtures';

let server: HttpServer; let io: Server;
let subscriptions: {market:string;symbol:string}[]=[]; let released=0;
let streamPrice=61234.56;
let acknowledge: (()=>void)|undefined;
test.beforeAll(async()=>{
  server=createServer();io=new Server(server,{cors:{origin:true}});
  io.on('connection',socket=>{
    socket.on('flow_subscribe',(selection,ack)=>{
      subscriptions.push(selection);
      acknowledge=()=>{
        ack({success:true,...selection,status:'WAITING'});
        setTimeout(()=>{
          const px=streamPrice;
          socket.emit('flow:health',{...selection,status:'STALE',connected:true,streams:[],lag_ms:20000,reconnects:0,book_resyncs:0,gap_events:0});
          socket.emit('flow:dom',{...selection,best_bid:px,best_ask:px*1.00001,spread:px*0.00001,spread_bps:0.1,mid:px*1.000005,bid_depth_n:1,ask_depth_n:2,book_imbalance:-0.33,walls:[],levels:[{price:px,bid_size:1,ask_size:0,bid_notional:px,ask_notional:0,is_wall:false,is_poc:false,traded_buy:0,traded_sell:0,depth_pct:0.5}]});
          socket.emit('flow:tape',{...selection,entries:[{ts:Date.now(),price:px,qty:1,quote_qty:px,side:'BUY',is_whale:false,size_bucket:'S',price_tick:'UP',aggressive_streak:1}]});
          socket.emit('flow:tape',{...selection,market:selection.market==='spot'?'futures':'spot',entries:[{ts:Date.now(),price:999999.99,qty:1,quote_qty:999999.99,side:'BUY',size_bucket:'S'}]});
        },100);
      };
    });
    socket.on('flow_unsubscribe',()=>{released++;});
    socket.on('disconnect',()=>{released++;});
  });
  await new Promise<void>(resolve=>server.listen(8107,'127.0.0.1',resolve));
});
test.afterAll(async()=>{await new Promise<void>(resolve=>io.close(()=>resolve()));});

test('real Socket.IO awaits underscore subscription ACK, hydrates selected market, ignores wrong market and releases subscription',async({page})=>{
  subscriptions=[];released=0;acknowledge=undefined; const hydrations:string[]=[];const orders:unknown[]=[];
  await page.route('**/api/**',async route=>{
    const url=new URL(route.request().url());let body:unknown={};
    if(url.pathname.includes('/flow/')) {hydrations.push(url.href);body={success:!url.pathname.endsWith('metrics')&&!url.pathname.endsWith('dom'),market:url.searchParams.get('market'),symbol:url.searchParams.get('symbol'),bars:[],entries:[],levels:[],frames:[]};}
    else if(url.pathname.endsWith('/instruments'))body={instruments:[]};
    else if(url.pathname.endsWith('/order/preview'))body={...route.request().postDataJSON(),approved:true,reason:'Fixture risk approved',checks:{funds:true},quantity:'0.001',price:'61234.56',notional:'61.23',testnet:true};
    else if(url.pathname==='/api/exchange/order'){orders.push(route.request().postDataJSON());body={success:true,status:'FILLED',executed_qty:0.001};}
    else body={market:'spot',symbol:'BTCUSDT',price:60000,bids:[],asks:[]};
    await route.fulfill({contentType:'application/json',body:JSON.stringify(body)});
  });
  await page.goto('/terminal');
  await expect.poll(()=>subscriptions.length).toBe(1);
  expect(subscriptions[0]).toMatchObject({market:'spot',symbol:'BTCUSDT'});
  expect(hydrations).toHaveLength(0);
  acknowledge!();
  await expect.poll(()=>hydrations.length).toBeGreaterThan(0);
  expect(hydrations.every(url=>url.includes('market=spot'))).toBeTruthy();
  await expect(page.getByText('61,234.56',{exact:false}).first()).toBeVisible();
  await expect(page.getByText('999999.99',{exact:false})).toHaveCount(0);
  await expect(page.getByText('STALE',{exact:true}).first()).toBeVisible();
  await page.getByRole('button',{name:'Stage limit at 61234.56'}).click();
  await expect(page.getByLabel('Limit price')).toHaveValue('61234.56');expect(orders).toHaveLength(0);
  await page.getByLabel('Order quantity').fill('0.001');
  await page.getByRole('button',{name:'Preview testnet order'}).click();expect(orders).toHaveLength(0);
  await page.getByRole('button',{name:'Confirm testnet order'}).click();await expect.poll(()=>orders.length).toBe(1);
  expect(orders[0]).toMatchObject({market:'spot',symbol:'BTCUSDT',order_type:'LIMIT',limit_price:61234.56,qty:0.001});
  await expect.poll(()=>hydrations.filter(url=>url.includes('/volume-profile?')).length,{timeout:8000}).toBeGreaterThan(1);
  await page.getByRole('button',{name:'Futures',exact:true}).click();
  await expect.poll(()=>subscriptions.length).toBe(2);
  expect(subscriptions[1].market).toBe('futures');
  await expect(page.getByText('61,234.56',{exact:false})).toHaveCount(0);
  acknowledge!();
  await expect.poll(()=>hydrations.filter(url=>url.includes('market=futures')).length).toBeGreaterThan(0);
  await page.goto('/history');await expect.poll(()=>released).toBeGreaterThan(1);
});


test('subcent DOM stages the exact nonzero limit without sending an order',async({page})=>{
  streamPrice=0.00000123;subscriptions=[];acknowledge=undefined;
  await fixtures(page);
  await page.route('**/api/market/quote?**',route=>route.fulfill({json:{market:'spot',symbol:'BTCUSDT',price:streamPrice}}));
  const orders:string[]=[];page.on('request',request=>{if(request.method()==='POST')orders.push(request.url());});
  await page.setViewportSize({width:390,height:900});await page.goto('/terminal');
  await expect.poll(()=>subscriptions.length).toBe(1);acknowledge!();
  const level=page.getByRole('button',{name:'Stage limit at 0.00000123'});await expect(level).toBeVisible();
  await expect(level).toContainText('0.00000123');await level.click();
  await expect(page.getByLabel('Limit price')).toHaveValue('0.00000123');expect(orders).toEqual([]);
  await captureFixture(page,'terminal-subcent-dom-390');
  streamPrice=61234.56;
});
