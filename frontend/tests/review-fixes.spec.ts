import { test, expect, type Page } from '@playwright/test';
import { fixtures } from './fixtures';
import { formatPrice } from '../src/lib/flow/flowFormat';

for(const [a,b] of [[1.2345,1.2346],[12.345,12.346],[100000000.0000001,100000000.0000002]])test(`fine prices ${a} and ${b} remain distinct`,()=>{
  expect(formatPrice(a).replaceAll(',','')).toBe(String(a));
  expect(formatPrice(b).replaceAll(',','')).toBe(String(b));
});

for(const [open,close] of [[1.2345,1.2346],[12.345,12.346]])test(`chart preserves adjacent prices ${open} and ${close}`,async({page})=>{
  await fixtures(page);
  await page.route('**/api/market/quote?**',route=>route.fulfill({json:{market:'spot',symbol:'BTCUSDT',price:close}}));
  await page.route('**/api/market/bars?**',route=>route.fulfill({json:{market:'spot',symbol:'BTCUSDT',bars:[{time:'2026-10-24T00:00:00Z',open,high:close,low:open,close,volume:10}]}}));
  await page.goto('/');
  await expect(page.getByText(`O: $${open}`,{exact:true})).toBeVisible();
  await expect(page.getByText(`C: $${close}`,{exact:true})).toBeVisible();
  await expect(page.getByTestId('header-price')).toHaveText(`$${close}`);
});

test('history preserves tiny and zero entries and labels legacy premium separately from unknown entry',async({page})=>{
  await fixtures(page);
  const trade={market:'spot',status:'CLOSED',proposal:{underlying:'TINYUSDT',strategy_type:'MASTER_ORDER_FLOW'},symbol:'TINYUSDT',realized_pnl:null};
  await page.route('**/api/trades?**',route=>route.fulfill({json:[
    {...trade,trade_id:'tiny',entry_price:0.00000123},
    {...trade,trade_id:'unknown',entry_price:null},
    {...trade,trade_id:'zero',entry_price:0,proposal:{...trade.proposal,net_premium:5}},
    {...trade,trade_id:'legacy',entry_price:null,proposal:{...trade.proposal,net_premium:0.00000456}},
  ]}));
  await page.goto('/history');
  const entry=(id:string)=>page.getByRole('row').filter({has:page.getByRole('cell',{name:id,exact:true})}).getByRole('cell').nth(4);
  await expect(entry('tiny')).toHaveText('$0.00000123');
  await expect(entry('unknown')).toHaveText('Unavailable');
  await expect(entry('zero')).toHaveText('$0');
  await expect(entry('legacy')).toContainText('Entry unavailable');
  await expect(entry('legacy')).toContainText('Legacy net premium: $0.00000456');
});

async function sampleMotion(page:Page,action:()=>Promise<unknown>){
  const frames=page.evaluate(()=>new Promise<{width:number;ys:number[]}[]>(resolve=>{
    const samples:{width:number;ys:number[]}[]=[];const end=performance.now()+650;
    const sample=()=>{
      samples.push({width:document.querySelector('.workspace-sidebar')!.getBoundingClientRect().width,ys:Array.from(document.querySelectorAll('main .workspace-page > div[style]')).map(el=>new DOMMatrixReadOnly(getComputedStyle(el).transform).m42)});
      if(performance.now()<end)requestAnimationFrame(sample);else resolve(samples);
    };requestAnimationFrame(sample);
  }));
  await action();return frames;
}

for(const reducedMotion of ['reduce','no-preference'] as const)test(`motion preference ${reducedMotion} controls actual sidebar and page movement`,async({page})=>{
  await fixtures(page);await page.setViewportSize({width:1440,height:1000});
  await page.emulateMedia({reducedMotion});await page.goto('/');
  await expect(page.getByTestId('header-price')).toContainText('60,000');
  const widths=await sampleMotion(page,()=>page.getByRole('button',{name:'Collapse Sidebar',exact:true}).click());
  const history=await sampleMotion(page,()=>page.getByRole('link',{name:'Order History',exact:true}).click());
  const intermediateWidths=widths.map(s=>s.width).filter(width=>width>68.25&&width<239.75);
  const intermediateTranslations=history.flatMap(s=>s.ys).filter(y=>y>0.05&&y<11.95);
  console.log('Actual motion frames',JSON.stringify({reducedMotion,widthFrames:widths.length,historyFrames:history.length,intermediateWidths,intermediateTranslations}));
  if(reducedMotion==='reduce'){
    expect.soft(intermediateWidths).toEqual([]);
    expect.soft(intermediateTranslations).toEqual([]);
  }else{
    expect(intermediateWidths.length).toBeGreaterThan(0);
    expect(intermediateTranslations.length).toBeGreaterThan(0);
  }
  await expect(page.getByRole('heading',{name:'SPOT Execution ledger',exact:true})).toBeVisible();
});

for(const width of [390,1440])for(const [open,close] of [[1.2345,1.2346],[12.345,12.346],[0.00000122,0.00000124]])test(`chart axis and cursor labels fit outside plot at ${width}px for ${open}/${close}`,async({page},testInfo)=>{
  await page.setViewportSize({width,height:1000});await fixtures(page);
  await page.route('**/api/market/quote?**',route=>route.fulfill({json:{market:'spot',symbol:'BTCUSDT',price:close}}));
  await page.route('**/api/market/bars?**',route=>route.fulfill({json:{market:'spot',symbol:'BTCUSDT',bars:[{time:'2026-10-24T00:00:00Z',open,high:close,low:open,close,volume:10}]}}));
  await page.goto('/');
  await expect(page.getByText(`O: $${open}`,{exact:true})).toBeVisible();
  await expect(page.getByText(`C: $${close}`,{exact:true})).toBeVisible();
  const chart=page.locator('svg[viewBox="0 0 800 260"]');await expect(chart).toBeVisible();
  const plotRight=Number(await chart.locator('line[stroke="#1f2128"]').first().getAttribute('x2'));
  const axis=chart.locator('text[fill="#5e6673"]').filter({hasText:/^\$/});
  await expect(axis).toHaveCount(5);
  const labels=await axis.evaluateAll(elements=>elements.map(el=>{const box=(el as SVGTextElement).getBBox();return {text:el.textContent?.trim(),left:box.x,right:box.x+box.width};}));
  expect(new Set(labels.map(label=>label.text)).size).toBe(5);
  for(const label of labels){expect.soft(label.left,label.text).toBeGreaterThanOrEqual(plotRight+2);expect.soft(label.right,label.text).toBeLessThanOrEqual(798);}
  const live=await chart.locator('g.pointer-events-none').first().locator('text').first().evaluate(el=>{const b=(el as SVGTextElement).getBBox();return {left:b.x,right:b.x+b.width};});
  expect.soft(live.left).toBeGreaterThanOrEqual(plotRight+2);expect.soft(live.right).toBeLessThanOrEqual(798);
  const rect=await chart.boundingBox();expect(rect).not.toBeNull();
  await page.mouse.move(rect!.x+rect!.width*0.4,rect!.y+rect!.height*0.55);
  await expect(chart.locator('circle')).toBeVisible();
  const cursor=chart.locator('g.pointer-events-none').last().locator('text').last();
  const cursorBox=await cursor.evaluate(el=>{const b=(el as SVGTextElement).getBBox();return {text:el.textContent?.trim(),left:b.x,right:b.x+b.width};});
  expect.soft(cursorBox.left).toBeGreaterThanOrEqual(plotRight+16);expect.soft(cursorBox.right).toBeLessThanOrEqual(798);
  const cursorValue=Number(cursorBox.text?.replaceAll(',',''));expect(cursorValue).toBeGreaterThanOrEqual(open);expect(cursorValue).toBeLessThanOrEqual(close);
  console.log('Chart geometry',JSON.stringify({width,open,close,plotRight,labels,live,cursor:cursorBox}));
  await chart.locator('..').screenshot({path:testInfo.outputPath('chart-price-gutter.png')});
});
