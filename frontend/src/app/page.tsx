"use client";

import { useEffect, useState, useCallback, useRef, useMemo, memo } from "react";
import io from "socket.io-client";
import { useMarket } from "@/components/MarketProvider";
import { OrderTicket } from "@/components/OrderTicket";
import { MarketDepth } from "@/components/MarketDepth";
import { formatMoney, readBars, readOrders, readPositions } from "@/lib/market";
import { motion, AnimatePresence } from "framer-motion";
import {
  Tooltip,
  ResponsiveContainer,
  BarChart,
  Bar
} from "recharts";
import { CandlestickChart } from "../components/CandlestickChart";
import { 
  CandlestickChart as CandleIcon, 
  LineChart as LineIcon, 
  RefreshCw, 
  Clock, 
  Trash2, 
  Award,
  Layers,
  Zap,
} from "lucide-react";
import {
  cancelExchangeOrder,
  cancelAllExchangeOrders,
  fillPendingTrade,
  getTradeHistory,
  getAutoTradingStatus,
  startAutoTrading,
  stopAutoTrading,
  triggerAutoTradingCycle,
  AutoTradingStatus,
  ExchangePosition,
  ExchangeOrder,
  ExchangeBar
} from "../lib/api";
import { TradeRecord } from "../lib/types";

interface AgentLog {
  id: string;
  time: string;
  agent: string;
  msg: string;
  isRisk: boolean;
  confidence: number;
}

type DockTab = "positions" | "pending" | "orders" | "debate" | "riskgate" | "history";

// VolHelix trades exactly one strategy: the Master Order Flow confluence gate
// (order blocks + fair value gaps + gamma walls). Regime changes only scale size.
const MASTER_STRATEGY = "MASTER_ORDER_FLOW";

const VolumeBarChart = memo(function VolumeBarChart({ bars }: { bars: ExchangeBar[] }) {
  return (
    <>
      <div className="px-3 py-1 bg-[#16171b] border-t border-[#1f2128] flex items-center justify-between text-[10px] font-mono text-[#878996]">
        <div className="flex items-center gap-2">
          <span className="font-bold text-[#f5f5f5]">Trading Volume (Vol)</span>
          <span className="text-[#5e6673]">|</span>
          <span>Green Bars = Base Volume Per Interval</span>
        </div>
        <span className="text-[#20b26c] font-semibold">
          Latest: {bars.length > 0 ? `${(bars[bars.length - 1].volume / 1000).toFixed(1)}K units` : "--"}
        </span>
      </div>

      <div className="h-16 w-full px-2 pb-2 bg-[#121214]">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={bars} margin={{ top: 5, right: 10, left: 0, bottom: 0 }}>
            <Tooltip
              contentStyle={{
                backgroundColor: "#18191f",
                border: "1px solid #26282f",
                borderRadius: "6px",
                fontFamily: "monospace",
                fontSize: "11px",
              }}
              formatter={(val) => [`${Number(val).toLocaleString()} units`, "Traded Volume"]}
              labelStyle={{ color: "#20b26c", fontWeight: "bold" }}
            />
            <Bar dataKey="volume" name="Volume" fill="#20b26c" opacity={0.65} radius={[2, 2, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </>
  );
});

export default function BybitTradingTerminal() {
  const [activeTab, setActiveTab] = useState<DockTab>("positions");
  const marketState=useMarket();
  const {market,symbol:selectedTicker}=marketState;
  const [closing,setClosing]=useState<ExchangePosition|null>(null);
  const account=marketState.account;
  const midPrice=marketState.quote?.price;
  const [readError,setReadError]=useState('');
  const [chartInterval, setChartInterval] = useState("1H");
  const [chartType, setChartType] = useState<"CANDLE" | "LINE">("CANDLE");
  const [autoTrading, setAutoTrading] = useState<AutoTradingStatus | null>(null);
  const [autoTradingUnavailable,setAutoTradingUnavailable]=useState(true);
  const applyAutoStatus=useCallback((status:AutoTradingStatus|null)=>{setAutoTradingUnavailable(!status);if(status)setAutoTrading(status);},[]);
  const [isTogglingAuto, setIsTogglingAuto] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [toastMsg, setToastMsg] = useState<string | null>(null);
  const [isFillingOrder, setIsFillingOrder] = useState<string | null>(null);

  const [ledger,setLedger]=useState<{market:string;positions:ExchangePosition[];orders:ExchangeOrder[];history:TradeRecord[]}>({market:'',positions:[],orders:[],history:[]});
  const positions=ledger.market===market?ledger.positions:[];
  const orders=useMemo(()=>ledger.market===market?ledger.orders:[],[ledger,market]);
  const tradeHistory=useMemo(()=>ledger.market===market?ledger.history:[],[ledger,market]);

  // Computed pending orders (queued for market open / awaiting fill)
  const pendingOrders = useMemo(() => {
    return orders.filter((o) => {
      const s = (o.status || "").toLowerCase();
      return ["accepted", "new", "pending_new", "held", "open", "calculated", "unknown", "dispatching", "partially_filled", "pending"].includes(s);
    });
  }, [orders]);

  // Computed closed trades for history & ledger analytics
  const closedTrades = useMemo(() => {
    return tradeHistory.filter((t) => ["closed", "cancelled"].includes((t.status || "").toLowerCase()));
  }, [tradeHistory]);

  const historyMetrics = useMemo(() => {
    const total = closedTrades.length;
    if (total === 0) {
      return { total: 0, netPnl: 0, winRate: 0, profitFactor: 0, wins: 0, losses: 0, avgWin: 0, avgLoss: 0 };
    }
    let wins = 0;
    let losses = 0;
    let grossWin = 0;
    let grossLoss = 0;
    let netPnl = 0;

    closedTrades.forEach((t) => {
      const pnl = t.realized_pnl ?? 0;
      netPnl += pnl;
      if (pnl > 0) {
        wins++;
        grossWin += pnl;
      } else if (pnl < 0) {
        losses++;
        grossLoss += Math.abs(pnl);
      }
    });

    const winRate = total > 0 ? (wins / total) * 100 : 0;
    const profitFactor = grossLoss > 0 ? grossWin / grossLoss : grossWin > 0 ? 99.9 : 0;
    const avgWin = wins > 0 ? grossWin / wins : 0;
    const avgLoss = losses > 0 ? grossLoss / losses : 0;

    return { total, netPnl, winRate, profitFactor, wins, losses, avgWin, avgLoss };
  }, [closedTrades]);
  const [bars, setBars] = useState<ExchangeBar[]>([]);
  const [logs,setLogs]=useState<AgentLog[]>([]);
  const selectionRef=useRef<AbortController|null>(null);
  useEffect(()=>{const controller=new AbortController();selectionRef.current=controller;return ()=>controller.abort();},[market]);

  const showToast = (text: string) => {
    setToastMsg(text);
    setTimeout(() => setToastMsg(null), 3500);
  };

  const refreshAccountAndPositions = useCallback(async () => {
    const signal=selectionRef.current?.signal;
    try {
      const [pos,ord,hist]=await Promise.all([readPositions(market,signal),readOrders(market,signal),getTradeHistory(market,signal)]);
      if(signal?.aborted)return false;
      setLedger({market,positions:pos.positions,orders:ord,history:hist});
      setReadError(pos.available?'':`STALE positions: ${pos.error || 'Account unavailable'}`);
      return pos.available;
    } catch(error) {if(!signal?.aborted){setReadError(`STALE account data: ${error instanceof Error?error.message:'Account unavailable'}`);setLedger(previous=>previous.market===market?{...previous,positions:previous.positions.map(position=>({...position,stale:true}))}:previous);}return false;}
  },[market]);

  // 1. Initial mount: Connect persistent socket and poll account every 10s
  useEffect(() => {
    let isMounted = true;
    const initialTimer = setTimeout(() => {
      if (isMounted) {
        refreshAccountAndPositions();
        getAutoTradingStatus().then((st) => {if(isMounted)applyAutoStatus(st);}).catch(() => {});
      }
    }, 0);

    const accInterval = setInterval(() => {
      if (isMounted) refreshAccountAndPositions();
    }, 10000);

    const autoInterval = setInterval(async () => {
      if (!isMounted) return;
      try {
        const st = await getAutoTradingStatus();
        if(isMounted)applyAutoStatus(st);
      } catch {
        // ignore
      }
    }, 4000);

    const socket = io(process.env.NEXT_PUBLIC_SOCKET_URL, {path:"/socket.io",transports:["websocket"]});
    socket.on("reasoning_event", (event) => {
      if (!isMounted) return;
      setLogs((prev) => [
        {
          id: Math.random().toString(36).substring(2, 9),
          time: new Date().toLocaleTimeString(),
          agent: event.agent || "System",
          msg: event.message || "",
          isRisk: event.agent === "RiskGate" || event.agent === "DevilsAdvocate",
          confidence: event.confidence ?? 0,
        },
        ...prev,
      ].slice(0, 40));
    });

    return () => {
      isMounted = false;
      clearTimeout(initialTimer);
      clearInterval(accInterval);
      clearInterval(autoInterval);
      socket.disconnect();
    };
  }, [refreshAccountAndPositions,applyAutoStatus]);

  useEffect(()=>{
    const controller=new AbortController();let alive=true;
    const clear=setTimeout(()=>setBars([]),0);
    const load=async()=>{try {const data=await readBars(market,selectedTicker,chartInterval,controller.signal);if(alive)setBars(data);}catch(error){if(alive){setBars([]);setReadError(error instanceof Error?error.message:'Chart unavailable');}}};
    void load();const timer=setInterval(load,5000);
    return ()=>{alive=false;controller.abort();clearTimeout(clear);clearInterval(timer);};
  },[market,selectedTicker,chartInterval]);

  useEffect(()=>{
    const clear=setTimeout(()=>{setClosing(null);setReadError('Loading account data');},0);
    return ()=>clearTimeout(clear);
  },[market]);

  const [isSyncing, setIsSyncing] = useState(false);

  const handleSyncExchange = async () => {
    setIsSyncing(true);
    const available=await refreshAccountAndPositions();
    marketState.refresh();
    setIsSyncing(false);
    showToast(available?"Binance positions & orders synchronized":"Account data unavailable; saved exposure retained as stale");
  };

  const handleFillPending = async (orderId:string) => {
    setIsFillingOrder(orderId);
    const res=await fillPendingTrade(orderId,undefined,market);
    showToast(res.success?'Exchange status reconciled':res.error || 'Reconciliation failed');
    await refreshAccountAndPositions();setIsFillingOrder(null);
  };

  const handleCancelOrder = async (orderId: string) => {
    try {
      const res = await cancelExchangeOrder(orderId,market,orders.find(order=>order.id===orderId)?.symbol);
      if (res && res.success) {
        showToast("Order cancelled successfully");
        await refreshAccountAndPositions();
      } else {
        showToast(res.error || "Failed to cancel order");
      }
    } catch {
      showToast("Error cancelling order");
    }
  };

  const handleCancelAllOrders = async () => {
    try {
      const res = await cancelAllExchangeOrders(market);
      if (res && res.success) {
        showToast(`Cancelled ${res.cancelled ?? 0} pending order(s)`);
        await refreshAccountAndPositions();
      } else {
        showToast("Failed to cancel orders");
      }
    } catch {
      showToast("Error cancelling orders");
    }
  };

  const handleToggleAutoTrading = async () => {
    if(!autoTrading?.is_running&&(market==='futures'||autoTradingUnavailable))return;
    setIsTogglingAuto(true);
    try {
      if (autoTrading?.is_running) {
        const result=await stopAutoTrading();
        if(!result.success)throw new Error('Stop request failed');
        showToast("Autonomous Auto-Trading Paused");
      } else {
        const result=await startAutoTrading(30);
        if(!result.success)throw new Error('Start request failed');
        showToast("Autonomous Auto-Trading Activated (Scanning Every 30s)");
      }
      const st = await getAutoTradingStatus();
      applyAutoStatus(st);
    } catch {
      showToast("Error updating auto-trading");
    } finally {
      setIsTogglingAuto(false);
    }
  };

  const handleTriggerCycleNow = async () => {
    if(market!=='spot')return;
    setIsSubmitting(true);
    try {
      showToast(`Scanning ${selectedTicker} for Master Strategy Confluence...`);
      const res = await triggerAutoTradingCycle(selectedTicker,market);
      if (!res.success) {
        showToast(res.reason || 'Scan unavailable; execution not confirmed');
      } else if (res.executed) {
        const detail = res.tp_reason ? ` [${res.tp_reason}]` : "";
        showToast(`Master Strategy Triggered on ${res.symbol || selectedTicker}! TP: $${res.take_profit_price?.toFixed(2)}${detail} | SL: $${res.stop_loss_price?.toFixed(2)}`);
        await refreshAccountAndPositions();
      } else if (res && !res.executed) {
        showToast(`Scan Complete for ${selectedTicker}: Criteria not met right now (${res.reason || "Score < 70%"}). Holding cash safely.`);
      } else {
        showToast(`Scan Finished for ${selectedTicker}`);
      }
      const st = await getAutoTradingStatus();
      applyAutoStatus(st);
    } catch {
      showToast(`Scan unavailable for ${selectedTicker}`);
    } finally {
      setIsSubmitting(false);
    }
  };



  return (
    <div className="space-y-3 select-none text-xs">
      {/* Toast Notification */}
      <AnimatePresence>
        {toastMsg && (
          <motion.div
            initial={{ opacity: 0, y: -20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            className="fixed top-16 right-6 z-50 px-4 py-2.5 rounded-lg bg-[#18191f] border border-[#f7a600] text-[#f7a600] font-mono text-xs shadow-2xl flex items-center gap-2"
          >
            <span className="w-2 h-2 rounded-full bg-[#f7a600] animate-ping" />
            <span>{toastMsg}</span>
          </motion.div>
        )}
      </AnimatePresence>

      <div className="trade-ticket flex flex-wrap justify-between gap-3 font-mono">
        <strong>{market.toUpperCase()} · {selectedTicker}</strong>
        <span>Equity: {account ? `$${formatMoney(account.equity)}` : 'Unavailable'}</span>
        <span>Buying power: {account ? `$${formatMoney(account.buying_power)}` : 'Unavailable'}</span>
        <span>Last: {formatMoney(midPrice)}</span>
        {readError&&<p role="status" className="w-full text-[#f7a600]">{readError}</p>}
      </div>

      {/* Main 3-Column Bybit Pro Terminal */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-3">
        {/* Left Column (8 cols): Chart + Trading Dock */}
        <div className="lg:col-span-8 space-y-3">
          {/* Bybit Chart Container */}
          <div className="rounded-lg bg-[#18191f] border border-[#26282f] flex flex-col overflow-hidden shadow-lg">
            {/* Chart Toolbar */}
            <div className="px-3 py-2 bg-[#1c1d22] border-b border-[#26282f] flex flex-wrap items-center justify-between gap-2 font-mono">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-bold text-[#f5f5f5]">{selectedTicker}</span>
                <span className="text-[#878996]">|</span>
                <div className="flex gap-1 text-[11px]">
                  {["1m", "5m", "15m", "1H", "4H", "1D"].map((int) => (
                    <button
                      key={int}
                      onClick={() => {
                        setChartInterval(int);
                      }}
                      className={`px-2 py-0.5 rounded cursor-pointer font-bold transition-colors ${
                        chartInterval === int
                          ? "bg-[#f7a600] text-[#121214] shadow-[0_0_6px_rgba(247,166,0,0.25)]"
                          : "text-[#878996] hover:bg-[#1c1d22] hover:text-[#f5f5f5]"
                      }`}
                    >
                      {int}
                    </button>
                  ))}
                </div>

                <span className="text-[#878996]">|</span>

                {/* Candles vs Line Graph Solid Toggle */}
                <div className="flex items-center gap-1 bg-[#121214] p-0.5 rounded border border-[#26282f]">
                  <button
                    onClick={() => setChartType("CANDLE")}
                    className={`flex items-center gap-1.5 px-2.5 py-1 rounded text-[11px] font-bold cursor-pointer transition-colors ${
                      chartType === "CANDLE"
                        ? "bg-[#f7a600] text-[#121214] shadow-[0_0_8px_rgba(247,166,0,0.3)]"
                        : "text-[#878996] hover:bg-[#1c1d22] hover:text-[#f5f5f5]"
                    }`}
                    title="Switch to Candlestick Chart"
                  >
                    <CandleIcon className="w-3.5 h-3.5" />
                    <span>Candles</span>
                  </button>
                  <button
                    onClick={() => setChartType("LINE")}
                    className={`flex items-center gap-1.5 px-2.5 py-1 rounded text-[11px] font-bold cursor-pointer transition-colors ${
                      chartType === "LINE"
                        ? "bg-[#f7a600] text-[#121214] shadow-[0_0_8px_rgba(247,166,0,0.3)]"
                        : "text-[#878996] hover:bg-[#1c1d22] hover:text-[#f5f5f5]"
                    }`}
                    title="Switch to Line Chart"
                  >
                    <LineIcon className="w-3.5 h-3.5" />
                    <span>Line</span>
                  </button>
                </div>
              </div>

              <div className="flex items-center gap-3 text-[11px] text-[#878996]">
                <span className="px-1.5 py-0.5 rounded bg-[#26282f] text-[#f7a600] font-semibold">
                  Production candles
                </span>
                <span>Bid: <strong className="text-[#20b26c]">{marketState.depth?.bids[0] ? formatMoney(marketState.depth.bids[0][0]) : "Unavailable"}</strong></span>
                <span>Ask: <strong className="text-[#ef454a]">{marketState.depth?.asks[0] ? formatMoney(marketState.depth.asks[0][0]) : "Unavailable"}</strong></span>
              </div>
            </div>

            {/* Price Chart (Interactive Candlesticks / Line with Zoom & Free Crosshairs) */}
            <CandlestickChart
              key={selectedTicker}
              data={bars}
              chartType={chartType}
              chartInterval={chartInterval}
              currentPrice={midPrice}
            />

            {/* Volume Sub-Chart */}
            <VolumeBarChart bars={bars} />
          </div>

          {/* Bottom Trading Dock (Bybit Style) */}
          <div className="rounded-lg bg-[#18191f] border border-[#26282f] overflow-hidden shadow-lg">
            {/* Dock Tabs Header */}
            <div className="px-3 bg-[#1c1d22] border-b border-[#26282f] flex items-center justify-between font-mono overflow-x-auto">
              <div className="flex gap-2 shrink-0">
                {[
                  { key: "positions", label: `Positions (${positions.length})` },
                  { key: "pending", label: `Pending Orders (${pendingOrders.length})` },
                  { key: "history", label: `History & Ledger (${closedTrades.length})` },
                  { key: "orders", label: `Broker Orders (${orders.length})` },
                  { key: "debate", label: "Agent Debate Stream" },
                  { key: "riskgate", label: "Server risk checks" },
                ].map((t) => (
                  <button
                    key={t.key}
                    onClick={() => setActiveTab(t.key as DockTab)}
                    className={`py-2.5 px-3 text-xs font-semibold relative transition-colors cursor-pointer whitespace-nowrap ${
                      activeTab === t.key
                        ? "text-[#f7a600]"
                        : "text-[#878996] hover:text-[#f5f5f5]"
                    }`}
                  >
                    {t.label}
                    {activeTab === t.key && (
                      <motion.div
                        layoutId="dockTabIndicator"
                        className="absolute bottom-0 left-0 right-0 h-0.5 bg-[#f7a600]"
                      />
                    )}
                  </button>
                ))}
              </div>

              <button
                onClick={handleSyncExchange}
                disabled={isSyncing}
                className="flex items-center gap-1.5 text-[11px] text-[#f7a600] hover:underline cursor-pointer font-mono disabled:opacity-50 shrink-0"
                title="Synchronize Live Paper Account"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${isSyncing ? "animate-spin" : ""}`} />
                <span>{isSyncing ? "Syncing..." : "Sync Binance"}</span>
              </button>
            </div>

            {/* Dock Content */}
            <div className="p-3 font-mono min-h-48">
              {activeTab === "positions" && (
                <div>
                  {positions.length === 0 ? (
                    <div className="text-center py-12 text-[#878996]">
                      <div className="w-12 h-12 mx-auto mb-3 rounded-full bg-[#1c1d22] border border-[#26282f] flex items-center justify-center text-[#f7a600]">
                        <Layers className="w-6 h-6" />
                      </div>
                      <p className="font-bold text-sm text-[#f5f5f5]">No Active Positions</p>
                      <p className="text-xs mt-1 text-[#878996] max-w-md mx-auto">
                        Confirmed exchange exposure appears here. Preview an order before submitting to testnet.
                      </p>
                      {pendingOrders.length > 0 && (
                        <button
                          onClick={() => setActiveTab("pending")}
                          className="mt-4 inline-flex items-center gap-2 px-3.5 py-1.5 rounded-lg bg-[#f7a600]/15 hover:bg-[#f7a600]/25 text-[#f7a600] border border-[#f7a600]/30 text-xs font-bold transition-all cursor-pointer"
                        >
                          <Clock className="w-3.5 h-3.5" />
                          <span>View {pendingOrders.length} Resting Limit Order{pendingOrders.length > 1 ? "s" : ""} in Pending Tab &rarr;</span>
                        </button>
                      )}
                    </div>
                  ) : (
                    <div className="overflow-x-auto">
                      <table className="w-full text-left text-xs">
                        <thead>
                          <tr className="border-b border-[#26282f] text-[#5e6673] uppercase text-[10px]">
                            <th className="py-2 px-2">Symbol</th>
                            <th className="py-2 px-2">Side</th>
                            <th className="py-2 px-2 text-right">Qty</th>
                            <th className="py-2 px-2 text-right">Avg Entry</th>
                            <th className="py-2 px-2 text-right">Current Mark</th>
                            <th className="py-2 px-2 text-right">Market Value</th>
                            <th className="py-2 px-2 text-right">Unrealized P&L</th>
                            <th className="py-2 px-2 text-right">Action</th>
                          </tr>
                        </thead>
                        <tbody>
                          {positions.map((pos) => (
                            <tr key={pos.trade_id || pos.id || pos.symbol} className="border-b border-[#26282f]/50 hover:bg-[#1c1d22]/50">
                              <td className="py-2.5 px-2 font-bold text-[#f5f5f5] flex items-center gap-1.5">
                                <span className="w-1.5 h-1.5 rounded-full bg-[#20b26c] animate-pulse" />
                                {pos.symbol} {pos.stale ? "STALE" : ""}
                              </td>
                              <td className="py-2.5 px-2">
                                <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${
                                  pos.side === "LONG" ? "bg-[#20b26c]/15 text-[#20b26c]" : "bg-[#ef454a]/15 text-[#ef454a]"
                                }`}>
                                  {pos.side}
                                </span>
                              </td>
                              <td className="py-2.5 px-2 text-right text-[#f5f5f5] font-semibold">{pos.qty}</td>
                              <td className="py-2.5 px-2 text-right text-[#878996]">${pos.avg_entry_price.toFixed(2)}</td>
                              <td className="py-2.5 px-2 text-right text-[#f5f5f5] font-bold">${formatMoney(pos.current_price)}</td>
                              <td className="py-2.5 px-2 text-right text-[#878996]">${formatMoney(pos.market_value)}</td>
                              <td className={`py-2.5 px-2 text-right font-bold ${
                                pos.unrealized_pl >= 0 ? "text-[#20b26c]" : "text-[#ef454a]"
                              }`}>
                                {pos.unrealized_pl >= 0 ? "+" : ""}${formatMoney(pos.unrealized_pl)} ({formatMoney(pos.unrealized_plpc)}%)
                              </td>
                              <td className="py-2.5 px-2 text-right">
                                <button
                                  onClick={() => setClosing(pos)}
                                  className="px-2.5 py-1 rounded bg-[#ef454a]/15 hover:bg-[#ef454a]/25 text-[#ef454a] border border-[#ef454a]/30 text-[10px] font-bold transition-all cursor-pointer"
                                  title="Close position and record to History & Ledger"
                                >
                                  Close Position
                                </button>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              )}

              {/* Dedicated Pending Orders Dock */}
              {activeTab === "pending" && (
                <div>
                  {pendingOrders.length === 0 ? (
                    <div className="text-center py-10 text-[#878996]">
                      <p className="font-semibold text-[#f5f5f5]">No Pending Orders on Broker</p>
                      <p className="text-[11px] mt-1">No pending orders recorded for this market.</p>
                    </div>
                  ) : (
                    <div>
                      <div className="mb-2.5 flex items-center justify-between">
                        <div className="flex items-center gap-2 text-xs text-[#878996]">
                          <span className="w-2 h-2 rounded-full bg-[#f7a600] animate-pulse" />
                          <span>
                            {pendingOrders.length} Order{pendingOrders.length > 1 ? "s" : ""} Resting / Queued on {market} Testnet
                          </span>
                        </div>
                        <button
                          onClick={handleCancelAllOrders}
                          className="flex items-center gap-1 px-2.5 py-1 rounded bg-[#ef454a]/15 text-[#ef454a] hover:bg-[#ef454a]/25 text-[11px] font-semibold transition-colors cursor-pointer"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                          <span>Cancel All Pending ({pendingOrders.length})</span>
                        </button>
                      </div>

                      <div className="overflow-x-auto">
                        <table className="w-full text-left text-xs">
                          <thead>
                            <tr className="border-b border-[#26282f] text-[#5e6673] uppercase text-[10px]">
                              <th className="py-2 px-2">Order ID</th>
                              <th className="py-2 px-2">Symbol</th>
                              <th className="py-2 px-2">Side</th>
                              <th className="py-2 px-2 text-right">Qty</th>
                              <th className="py-2 px-2 text-right">Type</th>
                              <th className="py-2 px-2 text-right">Price</th>
                              <th className="py-2 px-2 text-right">Status / Queue</th>
                              <th className="py-2 px-2 text-right">Time</th>
                              <th className="py-2 px-2 text-right">Action</th>
                            </tr>
                          </thead>
                          <tbody>
                            {pendingOrders.map((ord) => {
                              const s = (ord.status || "").toLowerCase();
                              let statusText = ord.status;
                              let statusBg = "bg-[#26282f] text-[#f7a600]";
                              if (s === "accepted") {
                                statusText = "QUEUED FOR OPEN";
                                statusBg = "bg-[#f7a600]/15 text-[#f7a600]";
                              } else if (s === "held") {
                                statusText = "BRACKET HELD";
                                statusBg = "bg-[#3a3b45] text-[#878996]";
                              } else if (s === "new" || s === "open") {
                                statusText = "RESTING LIMIT";
                                statusBg = "bg-[#20b26c]/15 text-[#20b26c]";
                              }

                              return (
                                <tr key={ord.id} className="border-b border-[#26282f]/50 hover:bg-[#1c1d22]/50">
                                  <td className="py-2 px-2 text-[#878996] text-[11px] truncate max-w-30" title={ord.id}>
                                    {ord.id.slice(0, 8)}...
                                  </td>
                                  <td className="py-2 px-2 font-bold text-[#f5f5f5]">{ord.symbol}</td>
                                  <td className="py-2 px-2">
                                    <span className={`px-1.5 py-0.2 rounded text-[10px] font-bold ${
                                      ord.side === "BUY" ? "text-[#20b26c]" : "text-[#ef454a]"
                                    }`}>
                                      {ord.side}
                                    </span>
                                  </td>
                                  <td className="py-2 px-2 text-right text-[#f5f5f5]">{ord.qty}</td>
                                  <td className="py-2 px-2 text-right text-[#878996]">
                                    {ord.type || "MARKET"}
                                  </td>
                                  <td className="py-2 px-2 text-right text-[#f5f5f5]">
                                    {ord.limit_price ? `$${ord.limit_price.toFixed(2)}` : (ord.stop_price ? `Stop $${ord.stop_price.toFixed(2)}` : "Market")}
                                  </td>
                                  <td className="py-2.5 px-2 text-right">
                                    <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${statusBg}`}>
                                      {statusText}
                                    </span>
                                  </td>
                                  <td className="py-2 px-2 text-right text-[#5e6673] text-[11px]">
                                    {ord.created_at ? new Date(ord.created_at).toLocaleTimeString() : "-"}
                                  </td>
                                  <td className="py-2 px-2 text-right">
                                    <div className="flex items-center justify-end gap-1.5">
                                      <button
                                        onClick={() => handleFillPending(ord.id)}
                                        disabled={isFillingOrder === ord.id}
                                        className="px-2 py-0.5 rounded bg-[#20b26c]/20 hover:bg-[#20b26c]/30 text-[#20b26c] border border-[#20b26c]/40 text-[10px] font-bold transition-all cursor-pointer disabled:opacity-50 flex items-center gap-1"
                                        title="Reconcile the actual exchange order state"
                                      >
                                        <Zap className={`w-2.5 h-2.5 ${isFillingOrder === ord.id ? "animate-spin" : ""}`} />
                                        <span>{isFillingOrder === ord.id ? "Filling..." : "Reconcile"}</span>
                                      </button>
                                      <button
                                        onClick={() => handleCancelOrder(ord.id)}
                                        className="px-2 py-0.5 rounded bg-[#26282f] hover:bg-[#ef454a]/20 hover:text-[#ef454a] text-[#878996] text-[10px] transition-colors cursor-pointer"
                                      >
                                        Cancel
                                      </button>
                                    </div>
                                  </td>
                                </tr>
                              );
                            })}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* Order History Dock */}
              {activeTab === "orders" && (
                <div>
                  {orders.length === 0 ? (
                    <div className="text-center py-10 text-[#878996]">No Orders Found on Binance</div>
                  ) : (
                    <div className="overflow-x-auto">
                      <table className="w-full text-left text-xs">
                        <thead>
                          <tr className="border-b border-[#26282f] text-[#5e6673] uppercase text-[10px]">
                            <th className="py-2 px-2">Order ID</th>
                            <th className="py-2 px-2">Symbol</th>
                            <th className="py-2 px-2">Side</th>
                            <th className="py-2 px-2 text-right">Qty</th>
                            <th className="py-2 px-2 text-right">Avg Price</th>
                            <th className="py-2 px-2 text-right">Status</th>
                            <th className="py-2 px-2 text-right">Time</th>
                          </tr>
                        </thead>
                        <tbody>
                          {orders.map((ord) => (
                            <tr key={ord.id} className="border-b border-[#26282f]/50 hover:bg-[#1c1d22]/50">
                              <td className="py-2 px-2 text-[#878996] text-[11px] truncate max-w-30">{ord.id}</td>
                              <td className="py-2 px-2 font-bold text-[#f5f5f5]">{ord.symbol}</td>
                              <td className="py-2 px-2">
                                <span className={`px-1.5 py-0.2 rounded text-[10px] font-bold ${
                                  ord.side === "BUY" ? "text-[#20b26c]" : "text-[#ef454a]"
                                }`}>
                                  {ord.side}
                                </span>
                              </td>
                              <td className="py-2 px-2 text-right text-[#f5f5f5]">{ord.qty}</td>
                              <td className="py-2 px-2 text-right text-[#878996]">
                                {ord.filled_avg_price ? `$${ord.filled_avg_price.toFixed(2)}` : "-"}
                              </td>
                              <td className="py-2 px-2 text-right">
                                <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${
                                  ord.status === "filled" ? "bg-[#20b26c]/15 text-[#20b26c]" : "bg-[#26282f] text-[#f7a600]"
                                }`}>
                                  {ord.status}
                                </span>
                              </td>
                              <td className="py-2 px-2 text-right text-[#5e6673] text-[11px]">
                                {new Date(ord.created_at).toLocaleTimeString()}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              )}

              {activeTab === "debate" && (
                <div className="space-y-2 max-h-56 overflow-y-auto">
                  {logs.map((log) => (
                    <div
                      key={log.id}
                      className="p-2.5 rounded bg-[#1c1d22] border border-[#26282f] flex items-start justify-between gap-3"
                    >
                      <div>
                        <div className="flex items-center gap-2 mb-1">
                          <span className={`font-bold text-[11px] ${log.isRisk ? "text-[#ef454a]" : "text-[#f7a600]"}`}>
                            {log.agent}
                          </span>
                          <span className="text-[10px] text-[#5e6673]">{log.time}</span>
                          <span className="px-1 py-0.2 rounded bg-[#26282f] text-[9px] text-[#878996]">
                            Confidence: {(log.confidence * 100).toFixed(0)}%
                          </span>
                        </div>
                        <p className="text-[#f5f5f5] text-[11px] leading-relaxed">{log.msg}</p>
                      </div>
                      <span className="px-2 py-0.5 rounded bg-[#20b26c]/15 text-[#20b26c] text-[10px] font-bold">
                        CONSENSUS
                      </span>
                    </div>
                  ))}
                </div>
              )}

              {activeTab === "riskgate" && <p>Risk checks are computed by the server for each order. Open the order preview to inspect the verdict, coverage and individual checks. A preview never guarantees execution.</p>}

              {activeTab === "history" && (
                <div className="space-y-4">
                  {/* Quantitative Performance Metrics Grid */}
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                    <div className="p-2.5 rounded-lg bg-[#1c1d22] border border-[#26282f]">
                      <div className="text-[10px] text-[#878996] uppercase font-semibold">Realized Net P&L</div>
                      <div className={`text-base font-black mt-0.5 ${historyMetrics.netPnl >= 0 ? "text-[#20b26c]" : "text-[#ef454a]"}`}>
                        {historyMetrics.netPnl >= 0 ? "+" : ""}${historyMetrics.netPnl.toFixed(2)}
                      </div>
                      <div className="text-[9px] text-[#5e6673] mt-0.5">{historyMetrics.total} Closed Trades</div>
                    </div>

                    <div className="p-2.5 rounded-lg bg-[#1c1d22] border border-[#26282f]">
                      <div className="text-[10px] text-[#878996] uppercase font-semibold">Win Rate</div>
                      <div className="text-base font-black text-[#f7a600] mt-0.5">
                        {historyMetrics.winRate.toFixed(1)}%
                      </div>
                      <div className="text-[9px] text-[#878996] mt-0.5">
                        {historyMetrics.wins}W / {historyMetrics.losses}L
                      </div>
                    </div>

                    <div className="p-2.5 rounded-lg bg-[#1c1d22] border border-[#26282f]">
                      <div className="text-[10px] text-[#878996] uppercase font-semibold">Profit Factor</div>
                      <div className="text-base font-black text-[#f5f5f5] mt-0.5">
                        {historyMetrics.profitFactor.toFixed(2)}x
                      </div>
                      <div className="text-[9px] text-[#5e6673] mt-0.5">Gross Win / Gross Loss</div>
                    </div>

                    <div className="p-2.5 rounded-lg bg-[#1c1d22] border border-[#26282f]">
                      <div className="text-[10px] text-[#878996] uppercase font-semibold">Avg Win / Avg Loss</div>
                      <div className="text-xs font-bold mt-1 flex items-center gap-1.5">
                        <span className="text-[#20b26c]">+${historyMetrics.avgWin.toFixed(2)}</span>
                        <span className="text-[#5e6673]">/</span>
                        <span className="text-[#ef454a]">-${historyMetrics.avgLoss.toFixed(2)}</span>
                      </div>
                      <div className="text-[9px] text-[#5e6673] mt-0.5">Risk-Reward Ratio</div>
                    </div>
                  </div>

                  {/* Complete Trade Ledger */}
                  {closedTrades.length === 0 ? (
                    <div className="text-center py-8 text-[#878996]">
                      <Award className="w-8 h-8 mx-auto mb-2 text-[#5e6673]" />
                      <p className="font-semibold text-[#f5f5f5]">No Closed Trades in Ledger</p>
                      <p className="text-[11px] mt-1">
                        When active positions are closed manually or exit via Take Profit / Stop Loss, their executed details and realized P&L feed directly into this analysis ledger.
                      </p>
                    </div>
                  ) : (
                    <div className="overflow-x-auto">
                      <div className="text-[10px] font-bold text-[#878996] uppercase mb-2 flex items-center justify-between">
                        <div className="flex items-center gap-1.5">
                          <span className="w-1.5 h-1.5 rounded-full bg-[#f7a600]" />
                          <span>Audited Trade Ledger ({closedTrades.length} Records)</span>
                        </div>
                        <span className="text-[9px] text-[#5e6673]">Sorted by Most Recent</span>
                      </div>
                      <table className="w-full text-left text-xs">
                        <thead>
                          <tr className="border-b border-[#26282f] text-[#5e6673] uppercase text-[10px]">
                            <th className="py-2 px-2">Trade ID</th>
                            <th className="py-2 px-2">Symbol</th>
                            <th className="py-2 px-2">Strategy</th>
                            <th className="py-2 px-2">Side</th>
                            <th className="py-2 px-2 text-right">Qty</th>
                            <th className="py-2 px-2 text-right">Entry</th>
                            <th className="py-2 px-2 text-right">Exit</th>
                            <th className="py-2 px-2 text-right">Realized P&L</th>
                            <th className="py-2 px-2 text-right">Exit Time</th>
                            <th className="py-2 px-2 text-right">Status</th>
                          </tr>
                        </thead>
                        <tbody>
                          {closedTrades.map((t, idx) => {
                            const pnl = t.realized_pnl;
                            const isWin = pnl != null && pnl >= 0;
                            const tradeId = t.trade_id || t.id || `TRD-REC-${idx}`;
                            const symbol = t.symbol || t.proposal?.underlying || "Unavailable";
                            const strategy = t.strategy || t.proposal?.strategy_type || MASTER_STRATEGY;
                            const side = t.side || t.proposal?.side || "—";
                            const qty = t.qty ?? t.proposal?.qty ?? "—";
                            const entryPrice = t.entry_price;
                            const exitPrice = t.exit_price;
                            const timeDisplay = t.exit_time ? new Date(t.exit_time).toLocaleTimeString() : (t.entry_time ? new Date(t.entry_time).toLocaleTimeString() : "-");
                            return (
                              <tr key={tradeId} className="border-b border-[#26282f]/50 hover:bg-[#1c1d22]/50">
                                <td className="py-2 px-2 text-[#878996] text-[11px] truncate max-w-25" title={tradeId}>
                                  {tradeId.slice(0, 8)}...
                                </td>
                                <td className="py-2 px-2 font-bold text-[#f5f5f5]">{symbol}</td>
                                <td className="py-2 px-2 text-[#878996] text-[11px]">{strategy}</td>
                                <td className="py-2 px-2">
                                  <span className={`px-1.5 py-0.2 rounded text-[10px] font-bold ${
                                    side === "BUY" ? "bg-[#20b26c]/15 text-[#20b26c]" : "bg-[#ef454a]/15 text-[#ef454a]"
                                  }`}>
                                    {side}
                                  </span>
                                </td>
                                <td className="py-2 px-2 text-right text-[#f5f5f5]">{qty}</td>
                                <td className="py-2 px-2 text-right text-[#878996]">
                                  {formatMoney(entryPrice)}
                                </td>
                                <td className="py-2 px-2 text-right text-[#f5f5f5] font-semibold">
                                  {formatMoney(exitPrice)}
                                </td>
                                <td className={`py-2 px-2 text-right font-bold ${isWin ? "text-[#20b26c]" : "text-[#ef454a]"}`}>
                                  {pnl==null?'—':`${isWin?'+':''}$${formatMoney(pnl)}`}
                                </td>
                                <td className="py-2 px-2 text-right text-[#5e6673] text-[11px]">
                                  {timeDisplay}
                                </td>
                                <td className="py-2 px-2 text-right">
                                  <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${
                                    isWin ? "bg-[#20b26c]/15 text-[#20b26c]" : "bg-[#ef454a]/15 text-[#ef454a]"
                                  }`}>
                                    {(t.status || "CLOSED").toUpperCase()}
                                  </span>
                                </td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Right Column (4 cols): Order Book + Order Execution Panel */}
        <div className="lg:col-span-4 space-y-3">
          <MarketDepth />
          {closing ? <OrderTicket key={`close:${closing.trade_id||closing.id}`} close={closing} onDismiss={()=>setClosing(null)} onUpdated={()=>{void refreshAccountAndPositions();marketState.refresh();}} /> : <OrderTicket key={`${market}:${selectedTicker}`} onUpdated={()=>{void refreshAccountAndPositions();marketState.refresh();}} />}
          <div className="trade-ticket">
                {/* 24/7 Autonomous Auto-Trader Loop Control & Strict Master Confluence Gate */}
                <div className="p-2.5 rounded-xl bg-[#141518] border border-[#2b313a] space-y-2">
                  {/* Master Strategy Auto-Pilot Toggle Header */}
                  <div className="flex items-center justify-between">
                    <div>
                      <div className="flex items-center gap-1.5">
                        <span className={`w-2 h-2 rounded-full ${autoTrading?.is_running ? "bg-[#0ecb81] animate-ping" : "bg-[#848e9c]"}`} />
                        <span className="text-xs font-black tracking-wide text-[#eaecef]">
                          SPOT AUTO-PILOT MODE
                        </span>
                      </div>
                      <div className="text-[9px] text-[#848e9c] mt-0.5">
                        Spot only · Master Strategy Confluence Gate {autoTradingUnavailable ? "· Status unavailable" : ""}
                      </div>
                    </div>

                    {/* Interactive Switch Component */}
                    <button
                      type="button"
                      role="switch"
                      aria-checked={autoTrading?.is_running || false}
                      onClick={handleToggleAutoTrading}
                      disabled={isTogglingAuto || (!autoTrading?.is_running&&(market==='futures'||autoTradingUnavailable))}
                      className={`relative inline-flex h-5 w-10 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none ${
                        autoTrading?.is_running ? "bg-[#0ecb81]" : "bg-[#2b313a]"
                      }`}
                      title={autoTrading?.is_running ? "Click to Pause Auto-Pilot" : "Click to Enable Auto-Pilot"}
                    >
                      <span
                        aria-hidden="true"
                        className={`pointer-events-none inline-block h-4 w-4 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out ${
                          autoTrading?.is_running ? "translate-x-5" : "translate-x-0"
                        }`}
                      />
                    </button>
                  </div>

                  {/* 24/7 Position Guardian & TP/SL Safeguard Badge */}
                  <div className="p-1.5 rounded-lg bg-[#0b0e11] border border-[#26282f] space-y-0.5 text-[9px]">
                    <div className="flex items-center justify-between">
                      <span className="flex items-center gap-1 text-[#848e9c]">
                        <span className="w-1.5 h-1.5 rounded-full bg-[#0ecb81] animate-pulse" />
                        <strong className="text-[#eaecef]">TP / SL Guardian:</strong>
                      </span>
                      <span className="px-1.5 py-0.5 rounded bg-[#0ecb81]/15 text-[#0ecb81] font-bold text-[8px]">
                        {autoTrading?.guardian_active ? "ACTIVE" : "UNAVAILABLE / INACTIVE"}
                      </span>
                    </div>
                    <div className="text-[8px] text-[#848e9c] leading-tight">
                      Application guardian requires the backend process. Check actual status above.
                    </div>
                  </div>

                  {/* Status & Strategy Rules Banner */}
                  <div className="p-1.5 rounded-lg bg-[#0b0e11] border border-[#26282f] space-y-1 text-[9px]">
                    <div className="flex items-center justify-between text-[#848e9c]">
                      <span>New Trades Allowed:</span>
                      <span className="px-1.5 py-0.5 rounded bg-[#f0b90b]/15 text-[#f0b90b] font-bold text-[8px]">
                        {autoTrading?.is_running ? "Auto-Pilot (Score ≥ 70%) & Scan" : "Manual Scan & Trade Only"}
                      </span>
                    </div>
                    <div className="flex items-center justify-between text-[#848e9c]">
                      <span>Setup Criteria:</span>
                      <span className="text-[#eaecef] font-mono text-[8px]">OB Retest + FVG Magnet + GEX Wall</span>
                    </div>
                    <div className="flex items-center justify-between text-[#848e9c]">
                      <span>Auto-Trades Executed:</span>
                      <strong className="text-[#0ecb81] font-bold text-[10px]">{autoTrading?.total_automated_trades ?? "—"}</strong>
                    </div>
                  </div>

                  {/* Live Radar Scanner Matrix (Watchlist Diagnostic Chips) */}
                  <div className="space-y-0.5">
                    <div className="flex items-center justify-between text-[9px] text-[#848e9c]">
                      <span>Live Watchlist Radar:</span>
                      <span className="text-[8px] font-mono text-[#5e6673]">
                        {autoTradingUnavailable ? "Status unavailable" : autoTrading?.is_running ? "Scanning Spot watchlist" : "Standby"}
                      </span>
                    </div>
                    <div className="grid grid-cols-5 gap-1">
                      {(autoTrading?.watched_symbols || []).map((ticker) => {
                        const diag = autoTrading?.scanner_diagnostics?.[ticker];
                        const score = diag ? Math.round(diag.score * 100) : null;
                        const isValid = diag?.is_valid || false;
                        const isSelected = selectedTicker === ticker;
                        return (
                          <div
                            key={ticker}
                            onClick={() => marketState.select("spot",ticker)}
                            className={`p-1 rounded text-center border text-[9px] cursor-pointer transition-all ${
                              isValid
                                ? "bg-[#0ecb81]/20 border-[#0ecb81] text-[#0ecb81] font-black"
                                : isSelected
                                ? "bg-[#2b313a] border-[#f0b90b] text-[#f0b90b] font-bold"
                                : score !== null
                                ? "bg-[#181a1f] border-[#2b313a] text-[#848e9c]"
                                : "bg-[#181a1f] border-[#26282f] text-[#5e6673]"
                            }`}
                            title={diag?.reasons?.join(" | ") || `Click to switch chart to ${ticker}`}
                          >
                            <div className="font-bold">{ticker}</div>
                            <div className="text-[8px] font-mono mt-0.5">
                              {score !== null ? `${score}%` : "Idle"}
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>

                  {/* Action Buttons: Enable/Pause Auto-Pilot AND Targeted Scan & Trade */}
                  <div className="grid grid-cols-2 gap-1.5 pt-0.5">
                    <button
                      onClick={handleToggleAutoTrading}
                      disabled={isTogglingAuto || (!autoTrading?.is_running&&(market==='futures'||autoTradingUnavailable))}
                      className={`py-2 px-2 rounded-lg font-bold text-[11px] transition-all cursor-pointer flex items-center justify-center gap-1.5 ${
                        autoTrading?.is_running
                          ? "bg-[#f6465d]/20 hover:bg-[#f6465d]/30 text-[#f6465d] border border-[#f6465d]/40"
                          : "bg-[#0ecb81] hover:bg-[#10dc8c] text-[#0b0e11] shadow-[0_0_10px_rgba(14,203,129,0.3)]"
                      }`}
                    >
                      {isTogglingAuto
                        ? "Updating..."
                        : autoTrading?.is_running
                        ? "Pause Auto-Pilot"
                        : "Enable Auto-Pilot"}
                    </button>

                    <button
                      onClick={handleTriggerCycleNow}
                      disabled={isSubmitting || market==='futures'}
                      className="py-2 px-2 rounded-lg bg-[#1e2329] hover:bg-[#2b313a] border border-[#2b313a] text-[#eaecef] font-bold text-[11px] transition-all cursor-pointer disabled:opacity-50 flex items-center justify-center gap-1.5"
                      title={`Evaluates ONLY the active chart symbol (${selectedTicker}) against Master Strategy confluence`}
                    >
                      {isSubmitting ? (
                        <>
                          <span className="w-1.5 h-1.5 rounded-full bg-[#f0b90b] animate-ping" />
                          <span>Scanning {selectedTicker}...</span>
                        </>
                      ) : (
                        market==='spot' ? `Scan & Trade (${selectedTicker})` : "Spot scanner only"
                      )}
                    </button>
                  </div>
                </div>

          </div>
        </div>
      </div>
    </div>
  );
}
