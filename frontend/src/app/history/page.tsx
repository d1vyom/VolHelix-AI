"use client";

import { useEffect, useState, useMemo, useCallback, useRef, Suspense } from "react";
import { useMarket } from '@/components/MarketProvider';
import { TrendingUp, BarChart, Package, Award, RefreshCw } from "lucide-react";
import { motion } from "framer-motion";
import {
  ResponsiveContainer,
  XAxis,
  YAxis,
  CartesianGrid,
  BarChart as RechartsBarChart,
  Bar,
  Tooltip,
} from "recharts";
import { getTrades } from "../../lib/api";
import { ExecutionFees } from '@/components/ExecutionFees';
import { formatMoney } from '@/lib/market';
import { TradeRecord } from "../../lib/types";

function TradeHistoryContent() {
  const {market}=useMarket();
  const selection=useRef<AbortController|null>(null);
  useEffect(()=>{const controller=new AbortController();selection.current=controller;return ()=>controller.abort();},[market]);
  const [ledger,setLedger]=useState<{market:string;trades:TradeRecord[]}>({market:'',trades:[]});
  const trades=useMemo(()=>ledger.market===market?ledger.trades:[],[ledger,market]);
  const [error,setError]=useState('');
  const [statusFilter, setStatusFilter] = useState("ALL");
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [lastUpdated, setLastUpdated] = useState<string>("");

  const fetchTrades = useCallback(async () => {
    const signal=selection.current?.signal;
    setIsRefreshing(true);
    try {
      const data = await getTrades(market,signal);
      if(signal?.aborted)return;
      setLedger({market,trades:Array.isArray(data)?data:[]});setError('');
      setLastUpdated(new Date().toLocaleTimeString());
    } catch {
      if(!signal?.aborted)setError('STALE ledger: trade data unavailable; showing last saved rows for this market.');
    } finally {
      setIsRefreshing(false);
    }
  }, [market]);

  useEffect(() => {
    let isMounted = true;
    const initialTimer = setTimeout(() => {
      if (isMounted) fetchTrades();
    }, 0);

    // Fast 3000ms polling so new bot executions appear automatically
    const interval = setInterval(() => {
      if (isMounted) fetchTrades();
    }, 3000);

    return () => {
      isMounted = false;
      clearTimeout(initialTimer);
      clearInterval(interval);
    };
  }, [fetchTrades]);

  const filteredTrades = useMemo(() => {
    return trades.filter((t) => {
      if (statusFilter === "ALL") return true;
      if (statusFilter === "OPEN") return t.status === "OPEN" || t.status === "FILLED";
      if (statusFilter === "CLOSED") return t.status === "CLOSED" || t.status === "TAKE_PROFIT";
      if (statusFilter === "TAKE_PROFIT") return t.status === "TAKE_PROFIT" || ((t.realized_pnl ?? 0) > 0);
      if (statusFilter === "STOPPED_OUT") return t.status === "STOPPED_OUT" || ((t.realized_pnl ?? 0) < 0);
      return t.status === statusFilter;
    });
  }, [trades, statusFilter]);

  const stats = useMemo(() => {
    const known = trades.filter(t => t.realized_pnl != null);
    const total = known.length;
    const wins = trades.filter((t) => (t.realized_pnl || 0) > 0);
    const losses = trades.filter((t) => (t.realized_pnl || 0) < 0);
    const totalPnL = known.reduce((sum, t) => sum + (t.realized_pnl || 0), 0);
    const winRate = total > 0 ? (wins.length / total) * 100 : 0;
    const grossProfit = wins.reduce((sum, t) => sum + Math.max(0, t.realized_pnl || 0), 0);
    const grossLoss = Math.abs(losses.reduce((sum, t) => sum + Math.min(0, t.realized_pnl || 0), 0));
    const profitFactor = grossLoss > 0 ? grossProfit / grossLoss : null;

    return {
      total,
      wins: wins.length,
      losses: losses.length,
      totalPnL: total ? totalPnL : null,
      winRate,
      profitFactor,
      avgWin: wins.length > 0 ? grossProfit / wins.length : 0,
      avgLoss: losses.length > 0 ? grossLoss / losses.length : 0,
    };
  }, [trades]);

  // Quantitative analytics computed from real ledger rows only.
  const strategyChartData = useMemo(() => {
    const groups: Record<string, { total: number; wins: number; pnl: number }> = {};
    trades.filter(t => t.realized_pnl != null).forEach((t) => {
      const rawType = t.proposal?.strategy_type || "UNCLASSIFIED";
      const name = rawType === "MASTER_ORDER_FLOW" ? "Master Flow" : rawType.replace(/_/g, " ");
      if (!groups[name]) {
        groups[name] = { total: 0, wins: 0, pnl: 0 };
      }
      groups[name].total += 1;
      if ((t.realized_pnl || 0) > 0) {
        groups[name].wins += 1;
      }
      groups[name].pnl += (t.realized_pnl || 0);
    });

    return Object.entries(groups).map(([strategy, data]) => ({
      strategy,
      winRate: data.total > 0 ? Math.round((data.wins / data.total) * 100) : 0,
      trades: data.total,
      pnl: Math.round(data.pnl),
    }));
  }, [trades]);

  return (
    <div className="workspace-page space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold tracking-tight text-[#eaecef] flex items-center gap-2.5">
            <span className="p-2 rounded-xl bg-[#f0b90b]/10 border border-[#f0b90b]/30 text-[#f0b90b]">
              <BarChart className="w-5 h-5" />
          </span>
          {market.toUpperCase()} Execution ledger
        </h1>
        <p className="text-xs text-[#848e9c] font-mono mt-1">
          Binance Testnet {market} execution records
        </p>
        </div>

        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-[#0ecb81]/10 border border-[#0ecb81]/30 text-[11px] font-mono text-[#0ecb81]">
            <span className="w-1.5 h-1.5 rounded-full bg-[#0ecb81] animate-pulse" />
            {error?'STALE / unavailable':'Poll every 3s'} {lastUpdated && `(${lastUpdated})`}
          </div>

          <button
            onClick={() => fetchTrades()}
            disabled={isRefreshing}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-[#181a20] border border-[#2b313a] hover:border-[#f0b90b]/50 text-xs font-mono text-[#eaecef] transition-all cursor-pointer disabled:opacity-50"
          >
            <RefreshCw className={`w-3.5 h-3.5 text-[#f0b90b] ${isRefreshing ? "animate-spin" : ""}`} />
            <span>Sync Ledger</span>
          </button>

          <div className="flex items-center gap-2 px-3 py-1.5 rounded-xl bg-[#181a20] border border-[#2b313a] text-xs font-mono text-[#eaecef]">
            <Award className="w-3.5 h-3.5 text-[#f0b90b]" />
            <span>Profit Factor: <strong className="text-[#f0b90b]">{stats.profitFactor == null ? '—' : stats.profitFactor.toFixed(2)}</strong></span>
          </div>
        </div>
      </div>

      {error&&<p role="status" className="text-[#f7a600]">{error}</p>}
      {/* 4 Stat Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="p-5 rounded-2xl bg-[#181a20] border border-[#2b313a] shadow-xl">
          <div className="text-xs font-mono text-[#848e9c] mb-1">REALIZED GROSS P&L</div>
          <div className={`text-3xl font-extrabold font-mono ${(stats.totalPnL ?? 0) >= 0 ? "text-[#0ecb81]" : "text-[#f6465d]"}`}>
            {stats.totalPnL == null ? "—" : `${stats.totalPnL >= 0 ? "+" : ""}$${formatMoney(stats.totalPnL)}`}
          </div>
          <div className="text-[11px] font-mono text-[#848e9c] mt-2">
            Fees excluded · Net P&L unavailable
            <span className="block mt-1">Known results: {stats.total} / {trades.length} records</span>
          </div>
        </div>

        <div className="p-5 rounded-2xl bg-[#181a20] border border-[#2b313a] shadow-xl">
          <div className="text-xs font-mono text-[#848e9c] mb-1">SYSTEM WIN RATE</div>
          <div className="text-3xl font-extrabold font-mono text-[#0ecb81]">
            {stats.total ? `${stats.winRate.toFixed(1)}%` : '—'}
          </div>
          <div className="text-[11px] font-mono text-[#848e9c] mt-2 flex items-center gap-2">
            <span className="text-[#0ecb81] font-semibold">{stats.wins} Wins</span>
            <span>/</span>
            <span className="text-[#f6465d] font-semibold">{stats.losses} Losses</span>
          </div>
        </div>

        <div className="p-5 rounded-2xl bg-[#181a20] border border-[#2b313a] shadow-xl">
          <div className="text-xs font-mono text-[#848e9c] mb-1">PROFIT FACTOR</div>
          <div className="text-3xl font-extrabold font-mono text-[#f0b90b]">
            {stats.profitFactor == null ? '—' : stats.profitFactor.toFixed(2)}
          </div>
          <div className="text-[11px] font-mono text-[#848e9c] mt-2">
            Gross Gain / Gross Loss
          </div>
        </div>

        <div className="p-5 rounded-2xl bg-[#181a20] border border-[#2b313a] shadow-xl">
          <div className="text-xs font-mono text-[#848e9c] mb-1">AVG WIN / AVG LOSS</div>
          <div className="text-2xl font-extrabold font-mono text-[#eaecef] flex items-center gap-2">
            <span className="text-[#0ecb81] text-lg">{stats.wins ? `+$${formatMoney(stats.avgWin)}` : '—'}</span>
            <span className="text-[#5e6673] text-sm">/</span>
            <span className="text-[#f6465d] text-lg">{stats.losses ? `-$${formatMoney(stats.avgLoss)}` : '—'}</span>
          </div>
          <div className="text-[11px] font-mono text-[#848e9c] mt-2">
            Payoff ratio: {stats.avgLoss > 0 && stats.wins ? `${(stats.avgWin / stats.avgLoss).toFixed(2)}x` : '—'}
          </div>
        </div>
      </div>

      {/* Strategy Performance Chart */}
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3 }}
        className="p-6 rounded-2xl bg-[#181a20] border border-[#2b313a] shadow-xl"
      >
        <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
          <div>
            <h3 className="font-semibold text-[#eaecef] flex items-center gap-2 text-base">
              <TrendingUp className="w-4 h-4 text-[#f0b90b]" />
              Gross win rate by strategy
            </h3>
            <p className="text-xs font-mono text-[#848e9c] mt-0.5">
              Historical win rate across executed Master Strategy positions
            </p>
          </div>
          <span className="px-2.5 py-1 rounded-lg bg-[#f0b90b]/15 text-[#f0b90b] border border-[#f0b90b]/30 text-xs font-mono font-bold">
            VolHelix Pro Execution
          </span>
        </div>

        {strategyChartData.length === 0 ? (
          <div className="h-60 w-full flex items-center justify-center text-xs font-mono text-[#848e9c] border border-dashed border-[#2b313a] rounded-xl">
            No executed trades yet — analytics populate after the first closed position.
          </div>
        ) : (
          <div className="h-60 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <RechartsBarChart data={strategyChartData} margin={{ top: 10, right: 10, left: -10, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#23272e" vertical={false} />
                <XAxis dataKey="strategy" stroke="#5e6673" fontSize={11} tickLine={false} axisLine={false} />
                <YAxis domain={[0, 100]} stroke="#5e6673" fontSize={11} tickFormatter={(v) => `${v}%`} tickLine={false} axisLine={false} />
                <Tooltip
                  contentStyle={{
                    backgroundColor: "#181a20",
                    border: "1px solid #2b313a",
                    borderRadius: "8px",
                    fontFamily: "monospace",
                    fontSize: "12px",
                  }}
                  labelStyle={{ color: "#f0b90b", fontWeight: 700 }}
                />
                <Bar dataKey="winRate" name="Win Rate %" fill="#f0b90b" radius={[6, 6, 0, 0]} isAnimationActive={false} />
              </RechartsBarChart>
            </ResponsiveContainer>
          </div>
        )}
      </motion.div>

      {/* Filter & Trade Table Section */}
      <motion.div
        initial={{ opacity: 0, y: 15 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.35, delay: 0.1 }}
        className="p-6 rounded-2xl bg-[#181a20] border border-[#2b313a] space-y-4 shadow-xl"
      >
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <h3 className="font-semibold text-[#eaecef] flex items-center gap-2 text-base">
              <Package className="w-4 h-4 text-[#f0b90b]" />
              Executed Trade Ledger
            </h3>
            <p className="text-xs font-mono text-[#848e9c] mt-0.5">
              Tracked positions and execution accounting on Binance Testnet
            </p>
          </div>

          {/* Filter Pills */}
          <div className="flex flex-wrap gap-2 text-xs font-mono">
            {["ALL", "TAKE_PROFIT", "STOPPED_OUT", "CLOSED", "OPEN"].map((st) => (
              <button
                key={st}
                onClick={() => setStatusFilter(st)}
                className={`px-3 py-1 rounded-lg transition-all font-bold ${
                  statusFilter === st
                    ? "bg-[#f0b90b] text-[#0b0e11]"
                    : "bg-[#1e2329] border border-[#2b313a] text-[#848e9c] hover:text-[#eaecef]"
                }`}
              >
                {st.replace(/_/g, " ")}
              </button>
            ))}
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full min-w-[1000px] text-xs font-mono">
            <thead>
              <tr className="border-b border-[#2b313a] text-[#848e9c] uppercase tracking-wider text-[10px]">
                <th className="text-left py-3 px-3">Trade / Order ID</th>
                <th className="text-left py-3 px-3">Symbol</th>
                <th className="text-left py-3 px-3">Strategy</th>
                <th className="text-left py-3 px-3">Dynamic TP / SL</th>
                <th className="text-right py-3 px-3">Entry Price / Size</th>
                <th className="text-right py-3 px-3">Gross P&L / native fees</th>
                <th className="text-right py-3 px-3">Date / Time</th>
                <th className="text-right py-3 px-3">Status</th>
              </tr>
            </thead>
            <tbody>
              {filteredTrades.length === 0 && (
                <tr>
                  <td colSpan={8} className="py-10 text-center text-[#848e9c]">
                    No trades match this filter. The ledger fills as soon as the Master Strategy opens a position.
                  </td>
                </tr>
              )}

              {filteredTrades.map((t) => {
                const pnl = t.realized_pnl;
                const tp = t.take_profit_price || t.proposal?.take_profit;
                const sl = t.stop_loss_price || t.proposal?.stop_loss;
                const displayId = t.trade_id.length > 14 ? `${t.trade_id.slice(0, 8)}...` : t.trade_id;

                return (
                  <tr key={t.trade_id} className="border-b border-[#2b313a]/40 hover:bg-[#1e2329]/60 transition-colors">
                    <td className="py-3.5 px-3 text-[#eaecef] font-semibold" title={t.trade_id}>
                      {displayId}
                    </td>
                    <td className="py-3.5 px-3 font-bold text-[#f0b90b]">{t.symbol || t.proposal?.underlying || 'Unavailable'}</td>
                    <td className="py-3.5 px-3 text-[#eaecef]">
                      {t.proposal?.strategy_type === "MASTER_ORDER_FLOW" ? (
                        <span className="inline-flex items-center gap-1.5 font-bold text-[#f0b90b] bg-[#f0b90b]/10 px-2 py-0.5 rounded border border-[#f0b90b]/30">
                          <span className="w-1.5 h-1.5 rounded-full bg-[#f0b90b] animate-pulse" />
                          Master Flow
                        </span>
                      ) : (
                        t.proposal?.strategy_type?.replace(/_/g, " ") || "—"
                      )}
                    </td>
                    <td className="py-3.5 px-3 text-[11px]">
                      {tp && sl ? (
                        <div className="flex items-center gap-2">
                          <span className="text-[#0ecb81] font-bold">TP: ${formatMoney(tp)}</span>
                          <span className="text-[#5e6673]">|</span>
                          <span className="text-[#f6465d] font-bold">SL: ${formatMoney(sl)}</span>
                        </div>
                      ) : (
                        <span className="text-[#848e9c]">Dynamic Anchor</span>
                      )}
                    </td>
                    <td className="py-3.5 px-3 text-right text-[#eaecef]">
                      ${t.entry_price ? t.entry_price.toLocaleString() : (t.proposal?.net_premium ? t.proposal.net_premium.toLocaleString() : "—")}
                    </td>
                    <td className={`py-3.5 px-3 text-right font-bold ${(pnl ?? 0) >= 0 ? "text-[#0ecb81]" : "text-[#f6465d]"}`}>
                      {pnl == null ? "Gross P&L unavailable" : `${pnl >= 0 ? "+" : ""}$${formatMoney(pnl)}`}<ExecutionFees record={t} />
                    </td>
                    <td className="py-3.5 px-3 text-right text-[#848e9c]">
                      {t.entry_time ? `${new Date(t.entry_time).toLocaleDateString()} ${new Date(t.entry_time).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}` : "—"}
                    </td>
                    <td className="py-3.5 px-3 text-right">
                      <span
                        className={`px-2 py-0.5 rounded text-[10px] font-bold border ${
                          t.status === "TAKE_PROFIT" || (t.status === "CLOSED" && (pnl ?? 0) > 0)
                            ? "bg-[#0ecb81]/15 text-[#0ecb81] border-[#0ecb81]/30"
                            : t.status === "STOPPED_OUT" || (pnl ?? 0) < 0
                            ? "bg-[#f6465d]/15 text-[#f6465d] border-[#f6465d]/30"
                            : t.status === "OPEN"
                            ? "bg-[#3b82f6]/15 text-[#3b82f6] border-[#3b82f6]/30"
                            : "bg-[#1e2329] text-[#848e9c] border-[#2b313a]"
                        }`}
                      >
                        {t.status}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </motion.div>
    </div>
  );
}

export default function TradeHistory() {
  return (
    <Suspense fallback={<div className="flex items-center justify-center h-[70vh] text-[#848e9c] font-mono text-sm">Calibrating Trade History...</div>}>
      <TradeHistoryContent />
    </Suspense>
  );
}
