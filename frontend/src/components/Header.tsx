"use client";
import Link from 'next/link';
import { MarketSelector } from './MarketSelector';
import { useMarket } from './MarketProvider';
import { formatMoney } from '@/lib/market';
export function Header() {
  const {market,symbol,quote,account,error,refresh}=useMarket();
  return <header className="workspace-header sticky top-0 z-30 border-b border-[#26282f] bg-[#121214] p-3 font-mono text-xs">
    <details className="md:hidden w-full">
      <summary className="cursor-pointer text-[#f7a600]">Workspace navigation</summary>
      <nav aria-label="Mobile workspace" className="flex flex-wrap gap-3 py-3">
        <Link href="/">Trading Terminal</Link><Link href="/terminal">Pro Terminal</Link><Link href="/history">Order History</Link><Link href="/volatility">Volatility Lab</Link><Link href="/audit">Risk Audit</Link>
      </nav>
    </details>
    <MarketSelector />
    <div className="flex flex-wrap items-center gap-3">
      <strong data-testid="selected-market">{market} · {symbol}</strong>
      <span data-testid="header-price" className="text-[#f7a600]">{quote ? `$${formatMoney(quote.price)}` : 'Quote unavailable'}</span>
      <span>Testnet cash: {account ? `$${formatMoney(account.cash)}` : 'Unavailable'}</span>
      <span className="text-[#878996]">Production data / Testnet orders</span>
    </div>
    {error&&<div data-testid="market-read-status" role="status" className="text-[#f7a600] flex gap-2 flex-wrap"><span>{error}</span><button type="button" onClick={refresh}>Retry data</button></div>}
  </header>;
}
