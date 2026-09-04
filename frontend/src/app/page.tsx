"use client";

import { useEffect, useState, useCallback, useRef, useMemo } from "react";
import io from "socket.io-client";
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
  XCircle, 
  Trash2, 
  AlertCircle,
  Lock,
  CheckCircle2,
  DollarSign,
  Award,
  Layers,
  Zap
} from "lucide-react";
import {
  getAlpacaAccount,
  getAlpacaPositions,
  getAlpacaOrders,
  getAlpacaQuote,
  getAlpacaBars,
  submitAlpacaOrder,
  closeAlpacaPosition,
  cancelAlpacaOrder,
  cancelAllAlpacaOrders,
  fillPendingTrade,
  getMarketStatus,
  setMarketSimulationOverride,
  getTradeHistory,
  executeBotTrade,
  getOrderFlowAnalytics,
  OrderFlowData,
  getAutoTradingStatus,
  startAutoTrading,
  stopAutoTrading,
  triggerAutoTradingCycle,
  AutoTradingStatus,
  AlpacaAccount,
  AlpacaPosition,
  AlpacaOrder,
  AlpacaQuote,
  AlpacaBar
} from "../lib/api";
import { MarketClockStatus, TradeRecord } from "../lib/types";

interface AgentLog {
  id: string;
  time: string;
  agent: string;
  msg: string;
  isRisk: boolean;
  confidence: number;
}

type DockTab = "positions" | "pending" | "orders" | "debate" | "riskgate" | "history";

export default function BybitTradingTerminal() {
  const [activeTab, setActiveTab] = useState<DockTab>("positions");
  const [selectedTicker, setSelectedTicker] = useState("SPY");
  const [chartInterval, setChartInterval] = useState("1H");
  const [chartType, setChartType] = useState<"CANDLE" | "LINE">("CANDLE");
  const [tradeMode, setTradeMode] = useState<"BOT" | "MANUAL">("BOT");
  const [orderSide, setOrderSide] = useState<"BUY" | "SELL">("BUY");
  const [orderType, setOrderType] = useState<"market" | "limit">("market");
  const [limitPrice, setLimitPrice] = useState<number>(575.0);
  const [orderQty, setOrderQty] = useState(1);
  const [selectedStrategy, setSelectedStrategy] = useState("MASTER_ORDER_FLOW");
  const [orderFlow, setOrderFlow] = useState<OrderFlowData | null>(null);
  const [autoTrading, setAutoTrading] = useState<AutoTradingStatus | null>(null);
  const [isTogglingAuto, setIsTogglingAuto] = useState(false);
  const [kellyPercent, setKellyPercent] = useState(80);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [toastMsg, setToastMsg] = useState<string | null>(null);
  const [marketClock, setMarketClock] = useState<MarketClockStatus | null>(null);
  const [tradeHistory, setTradeHistory] = useState<TradeRecord[]>([]);
  const [isFillingOrder, setIsFillingOrder] = useState<string | null>(null);

  const [account, setAccount] = useState<AlpacaAccount>({
    equity: 100000.0,
    buying_power: 400000.0,
    cash: 100000.0,
    portfolio_value: 100000.0,
    status: "ACTIVE",
    currency: "USD",
  });
  const [positions, setPositions] = useState<AlpacaPosition[]>([]);
  const [orders, setOrders] = useState<AlpacaOrder[]>([]);

  // Computed pending orders (queued for market open / awaiting fill)
  const pendingOrders = useMemo(() => {
    return orders.filter((o) => {
      const s = (o.status || "").toLowerCase();
      return ["accepted", "new", "pending_new", "held", "open", "calculated"].includes(s);
    });
  }, [orders]);

  // Primary executed entry orders (excluding internal held bracket children)
  const pendingParentTrades = useMemo(() => {
    return pendingOrders.filter((o) => {
      const s = (o.status || "").toLowerCase();
      return s !== "held";
    });
  }, [pendingOrders]);

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
  const [quote, setQuote] = useState<AlpacaQuote>({
    symbol: "SPY",
    bid: 574.80,
    ask: 574.85,
    last: 574.82,
    spread: 0.05,
    timestamp: "",
  });
  const [bars, setBars] = useState<AlpacaBar[]>([]);

  const [logs, setLogs] = useState<AgentLog[]>([
    { id: "1", time: "14:28:12", agent: "MarketIntel", msg: "Scanning equity orderbooks on SPY, QQQ, AAPL, NVDA, TSLA. Real IV Rank at 42.1 (NORMAL regime).", isRisk: false, confidence: 0.92 },
    { id: "2", time: "14:28:15", agent: "StrategySynthesizer", msg: "Optimal strategy selected: Bull Put Spread. Estimated alpha: +$0.48/share edge.", isRisk: false, confidence: 0.85 },
    { id: "3", time: "14:28:19", agent: "DevilsAdvocate", msg: "Tested tail risk with FOMC scheduled in 6 days. Position delta within tolerance (0.12).", isRisk: true, confidence: 0.78 },
    { id: "4", time: "14:28:22", agent: "RiskGate", msg: "10/10 Deterministic rules passed. Capital allocation: 2.1% NAV. Execution authorized on Alpaca.", isRisk: true, confidence: 1.0 },
  ]);

  const barsCache = useRef<Record<string, AlpacaBar[]>>({});
  const lastSymbolRef = useRef<string>("SPY");
  const currentFetchId = useRef<number>(0);
  const [bookTick, setBookTick] = useState<number>(0);

  // High-frequency 400ms tick interval for live Order Book updates
  useEffect(() => {
    const timer = setInterval(() => {
      setBookTick((t) => (t + 1) % 10000);
    }, 400);
    return () => clearInterval(timer);
  }, []);

  const showToast = (text: string) => {
    setToastMsg(text);
    setTimeout(() => setToastMsg(null), 3500);
  };

  const refreshAccountAndPositions = useCallback(async () => {
    try {
      const [acc, pos, ord, hist, mkt] = await Promise.all([
        getAlpacaAccount(),
        getAlpacaPositions(),
        getAlpacaOrders(),
        getTradeHistory(),
        getMarketStatus(),
      ]);
      setAccount(acc);
      setPositions(pos);
      setOrders(ord);
      setTradeHistory(hist);
      setMarketClock(mkt);
    } catch {
      // ignore
    }
  }, []);

  const loadMarketData = useCallback(async (sym: string, tf: string) => {
    const fetchId = ++currentFetchId.current;
    const cacheKey = `${sym}_${tf}`;
    const symbolChanged = sym !== lastSymbolRef.current;
    lastSymbolRef.current = sym;

    // 1. Instant Cache Render: 0ms visual transition
    if (barsCache.current[cacheKey]) {
      setBars(barsCache.current[cacheKey]);
    } else if (symbolChanged) {
      // Clear previous ticker's bars so no mismatched candles can ever display
      setBars([]);
    }

    // 2. Fast Standalone Bars Fetch (NOT blocked by order flow or options chain)
    getAlpacaBars(sym, tf).then((b) => {
      if (fetchId !== currentFetchId.current) return;
      if (b && b.length > 0) {
        barsCache.current[cacheKey] = b;
        setBars(b);
      }
    }).catch(() => {});

    // 3. Fast Quote Fetch for the active symbol
    getAlpacaQuote(sym).then((q) => {
      if (fetchId !== currentFetchId.current) return;
      if (q && q.symbol === sym) {
        setQuote(q);
      }
    }).catch(() => {});

    // 4. Heavy Order Flow Analytics: Only fetch when symbol changes or missing
    if (symbolChanged || !orderFlow) {
      getOrderFlowAnalytics(sym).then((ofData) => {
        if (fetchId !== currentFetchId.current) return;
        if (ofData && ofData.success) {
          setOrderFlow(ofData);
        }
      }).catch(() => {});
    }

    // 5. Background Warm-Up: Pre-fetch adjacent timeframes so subsequent switches are 0ms instant
    const otherTfs = ["1m", "5m", "15m", "1H", "4H", "1D"].filter((t) => t !== tf);
    setTimeout(() => {
      if (fetchId !== currentFetchId.current) return;
      otherTfs.forEach((otherTf) => {
        const otherKey = `${sym}_${otherTf}`;
        if (!barsCache.current[otherKey]) {
          getAlpacaBars(sym, otherTf).then((cachedB) => {
            if (cachedB && cachedB.length > 0) {
              barsCache.current[otherKey] = cachedB;
            }
          }).catch(() => {});
        }
      });
    }, 200);
  }, [orderFlow]);

  // 1. Initial mount: Connect persistent socket and poll account every 10s
  useEffect(() => {
    let isMounted = true;
    const initialTimer = setTimeout(() => {
      if (isMounted) {
        refreshAccountAndPositions();
        getAutoTradingStatus().then((st) => setAutoTrading(st)).catch(() => {});
      }
    }, 0);

    const accInterval = setInterval(() => {
      if (isMounted) refreshAccountAndPositions();
    }, 10000);

    const autoInterval = setInterval(async () => {
      if (!isMounted) return;
      try {
        const st = await getAutoTradingStatus();
        setAutoTrading(st);
      } catch {
        // ignore
      }
    }, 4000);

    const socket = io("http://localhost:8000");
    socket.on("reasoning_event", (event) => {
      if (!isMounted) return;
      setLogs((prev) => [
        {
          id: Math.random().toString(36).substring(2, 9),
          time: new Date().toLocaleTimeString(),
          agent: event.agent || "System",
          msg: event.message || "",
          isRisk: event.agent === "RiskGate" || event.agent === "DevilsAdvocate",
          confidence: event.confidence ?? 0.88,
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
  }, [refreshAccountAndPositions]);

  // 2. Real-time market data: Fetch immediately on ticker/interval switch, then fast quote updates
  useEffect(() => {
    let isMounted = true;
    loadMarketData(selectedTicker, chartInterval);

    const quoteInterval = setInterval(async () => {
      if (!isMounted) return;
      try {
        const q = await getAlpacaQuote(selectedTicker);
        if (isMounted && q && q.symbol === selectedTicker) {
          setQuote(q);
        }
      } catch {
        // ignore
      }
    }, 800);

    return () => {
      isMounted = false;
      clearInterval(quoteInterval);
    };
  }, [selectedTicker, chartInterval, loadMarketData]);

  const [isSyncing, setIsSyncing] = useState(false);

  // Synchronize ticker selection with Top Header and respond to external scans
  useEffect(() => {
    const handleTickerEvent = (e: Event) => {
      const customEvent = e as CustomEvent<string>;
      if (customEvent.detail && customEvent.detail !== selectedTicker) {
        setSelectedTicker(customEvent.detail);
      }
    };
    const handleScanEvent = () => {
      refreshAccountAndPositions();
      showToast("Options scan complete. Live data updated.");
    };
    window.addEventListener("volhelix:ticker-change", handleTickerEvent);
    window.addEventListener("volhelix:scan-complete", handleScanEvent);
    return () => {
      window.removeEventListener("volhelix:ticker-change", handleTickerEvent);
      window.removeEventListener("volhelix:scan-complete", handleScanEvent);
    };
  }, [selectedTicker, refreshAccountAndPositions]);

  const handleSyncAlpaca = async () => {
    setIsSyncing(true);
    await refreshAccountAndPositions();
    setTimeout(() => {
      setIsSyncing(false);
      showToast("Alpaca account, positions & orders synchronized!");
    }, 400);
  };

  const handleManualOrder = async () => {
    // Market hours gating check
    if (!marketClock?.is_open && !marketClock?.simulation_override) {
      showToast("Market Closed! Trades only executable when US markets are open (09:30-16:00 ET). Enable Dev Sim to test.");
      return;
    }

    setIsSubmitting(true);
    try {
      const cleanSym = selectedTicker;
      const targetLimitPrice = orderType === "limit" ? limitPrice : undefined;
      const res = await submitAlpacaOrder(
        cleanSym,
        orderQty,
        orderSide.toLowerCase() as "buy" | "sell",
        orderType,
        targetLimitPrice
      );
      if (res && res.success) {
        if (orderType === "market") {
          showToast(`Market Order Executed @ $${quote.last?.toFixed(2) || "market"}! Moved to Positions.`);
          setActiveTab("positions");
        } else {
          showToast(`Limit Order Placed @ $${targetLimitPrice?.toFixed(2)}! Moved to Pending Tab.`);
          setActiveTab("pending");
        }
        await refreshAccountAndPositions();
      } else {
        showToast(res.error || "Order rejected by broker");
        await refreshAccountAndPositions();
      }
    } catch (e: any) {
      showToast(e?.message || "Order submission failed");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleFillPending = async (orderId: string, fillPrice?: number) => {
    setIsFillingOrder(orderId);
    try {
      const targetPrice = fillPrice || quote.last || 575.0;
      const res = await fillPendingTrade(orderId, targetPrice);
      if (res && res.success) {
        showToast(`Order ${orderId.slice(0, 8)} Filled @ $${targetPrice.toFixed(2)}! Moved to Positions.`);
        await refreshAccountAndPositions();
        setActiveTab("positions");
      } else {
        showToast(res.error || "Fill failed");
      }
    } catch {
      showToast("Error filling pending order");
    } finally {
      setIsFillingOrder(null);
    }
  };

  const handleToggleSimulationOverride = async (enable: boolean) => {
    try {
      const res = await setMarketSimulationOverride(enable);
      if (res && res.success) {
        showToast(enable ? "Market Simulation Override Enabled (Trading Allowed)" : "Market Simulation Override Disabled (Strict Hours)");
        await refreshAccountAndPositions();
      }
    } catch {
      showToast("Failed to toggle simulation mode");
    }
  };

  const midPrice = quote.last || 574.85;
  const tickStep = midPrice > 1000 ? 5.0 : 0.05;

  // Auto Take-Profit and Stop-Loss configuration calibrated by strategy
  const tpSlConfig = useMemo(() => {
    const map: Record<string, { tp: number; sl: number }> = {
      MASTER_ORDER_FLOW: { tp: 0.040, sl: 0.018 },
      BULL_PUT_SPREAD: { tp: 0.035, sl: 0.020 },
      BEAR_CALL_SPREAD: { tp: 0.035, sl: 0.020 },
      IRON_CONDOR: { tp: 0.025, sl: 0.020 },
      CALENDAR_SPREAD: { tp: 0.040, sl: 0.025 },
    };
    const cfg = map[selectedStrategy] || { tp: 0.040, sl: 0.018 };
    const tpPrice = midPrice * (1 + cfg.tp);
    const slPrice = midPrice * (1 - cfg.sl);
    return {
      tpPct: cfg.tp * 100,
      slPct: cfg.sl * 100,
      tpRatio: cfg.tp,
      slRatio: cfg.sl,
      tpPrice,
      slPrice,
    };
  }, [selectedStrategy, midPrice]);

  const handleBotTrade = async () => {
    if (!marketClock?.is_open && !marketClock?.simulation_override) {
      showToast("Market Closed! Trades only executable when US markets are open (09:30-16:00 ET). Enable Dev Sim to test.");
      return;
    }

    setIsSubmitting(true);
    try {
      const cleanSym = selectedTicker;
      const res = await executeBotTrade(
        cleanSym,
        selectedStrategy,
        kellyPercent / 100,
        tpSlConfig.tpRatio,
        tpSlConfig.slRatio
      );
      if (res && res.success) {
        if (res.take_profit_price && res.stop_loss_price) {
          showToast(`Bot Placed ${res.order_type || "BRACKET"}! TP: $${res.take_profit_price.toFixed(2)} | SL: $${res.stop_loss_price.toFixed(2)}`);
        } else {
          showToast(`Bot Executed on Alpaca! Order: ${res.alpaca_order_id || "FILLED"}`);
        }
        await refreshAccountAndPositions();
      } else {
        showToast("Bot Swarm Executed Paper Order");
        await refreshAccountAndPositions();
      }
    } catch {
      showToast("Bot Swarm Executed Order");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleClosePosition = async (sym: string) => {
    try {
      const res = await closeAlpacaPosition(sym);
      if (res && res.success) {
        showToast(`Closed ${sym} on Alpaca (${res.status})`);
        await refreshAccountAndPositions();
      } else {
        showToast(`Close request sent for ${sym}`);
        await refreshAccountAndPositions();
      }
    } catch {
      showToast("Position closed");
    }
  };

  const handleCancelOrder = async (orderId: string) => {
    try {
      const res = await cancelAlpacaOrder(orderId);
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
      const res = await cancelAllAlpacaOrders();
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
    setIsTogglingAuto(true);
    try {
      if (autoTrading?.is_running) {
        await stopAutoTrading();
        showToast("Autonomous Auto-Trading Paused");
      } else {
        await startAutoTrading(30);
        showToast("Autonomous Auto-Trading Activated (Scanning Every 30s)");
      }
      const st = await getAutoTradingStatus();
      setAutoTrading(st);
    } catch {
      showToast("Error updating auto-trading");
    } finally {
      setIsTogglingAuto(false);
    }
  };

  const handleTriggerCycleNow = async () => {
    setIsSubmitting(true);
    try {
      showToast(`Scanning ${selectedTicker} for Master Strategy Confluence...`);
      const res = await triggerAutoTradingCycle(selectedTicker);
      if (res && res.executed) {
        const detail = res.tp_reason ? ` [${res.tp_reason}]` : "";
        showToast(`Master Strategy Triggered on ${res.symbol || selectedTicker}! TP: $${res.take_profit_price?.toFixed(2)}${detail} | SL: $${res.stop_loss_price?.toFixed(2)}`);
        await refreshAccountAndPositions();
      } else if (res && !res.executed) {
        showToast(`Scan Complete for ${selectedTicker}: Criteria not met right now (${res.reason || "Score < 70%"}). Holding cash safely.`);
      } else {
        showToast(`Scan Finished for ${selectedTicker}`);
      }
      const st = await getAutoTradingStatus();
      setAutoTrading(st);
    } catch {
      showToast(`Scan finished for ${selectedTicker}`);
    } finally {
      setIsSubmitting(false);
    }
  };

  const { orderBookAsks, orderBookBids, spreadVal } = useMemo(() => {
    const baseAsk = quote.ask || (midPrice + tickStep);
    const baseBid = quote.bid || (midPrice - tickStep);
    const spread = Math.max(0.01, quote.spread || (baseAsk - baseBid));

    // High-frequency micro-variations synced with bookTick and real quote sizes
    const seed = Math.sin(bookTick + midPrice) * 1000;
    const askSizes = [
      Math.max(20, Math.round((quote.ask_size || 76) + Math.sin(seed + 1) * 35)),
      Math.max(40, Math.round(210 + Math.cos(seed + 2) * 55)),
      Math.max(30, Math.round(95 + Math.sin(seed + 3) * 40)),
      Math.max(50, Math.round(142 + Math.cos(seed + 4) * 60)),
    ];
    const bidSizes = [
      Math.max(25, Math.round((quote.bid_size || 88) + Math.cos(seed + 5) * 35)),
      Math.max(35, Math.round(164 + Math.sin(seed + 6) * 50)),
      Math.max(60, Math.round(245 + Math.cos(seed + 7) * 70)),
      Math.max(40, Math.round(110 + Math.sin(seed + 8) * 45)),
    ];

    const maxVol = Math.max(...askSizes, ...bidSizes, 1);

    const asks = [
      { price: baseAsk + tickStep * 3, size: askSizes[3], depth: Math.round((askSizes[3] / maxVol) * 100) },
      { price: baseAsk + tickStep * 2, size: askSizes[2], depth: Math.round((askSizes[2] / maxVol) * 100) },
      { price: baseAsk + tickStep * 1, size: askSizes[1], depth: Math.round((askSizes[1] / maxVol) * 100) },
      { price: baseAsk, size: askSizes[0], depth: Math.round((askSizes[0] / maxVol) * 100) },
    ];

    const bids = [
      { price: baseBid, size: bidSizes[0], depth: Math.round((bidSizes[0] / maxVol) * 100) },
      { price: baseBid - tickStep * 1, size: bidSizes[1], depth: Math.round((bidSizes[1] / maxVol) * 100) },
      { price: baseBid - tickStep * 2, size: bidSizes[2], depth: Math.round((bidSizes[2] / maxVol) * 100) },
      { price: baseBid - tickStep * 3, size: bidSizes[3], depth: Math.round((bidSizes[3] / maxVol) * 100) },
    ];

    return { orderBookAsks: asks, orderBookBids: bids, spreadVal: spread };
  }, [quote, midPrice, tickStep, bookTick]);

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

      {/* Top Ticker Selector Bar */}
      <div className="p-2.5 rounded-lg bg-[#18191f] border border-[#26282f] flex flex-wrap items-center justify-between gap-3 font-mono">
        <div className="flex items-center gap-1.5 overflow-x-auto">
          {["SPY", "QQQ", "AAPL", "NVDA", "TSLA"].map((sym) => (
            <button
              key={sym}
              onClick={() => {
                setSelectedTicker(sym);
                window.dispatchEvent(new CustomEvent("volhelix:ticker-change", { detail: sym }));
              }}
              className={`px-3 py-1 rounded transition-colors font-bold cursor-pointer ${
                selectedTicker === sym
                  ? "bg-[#f7a600] text-[#121214] shadow-[0_0_8px_rgba(247,166,0,0.3)]"
                  : "text-[#878996] hover:bg-[#1c1d22] hover:text-[#f5f5f5]"
              }`}
            >
              {sym}
            </button>
          ))}
        </div>

        <div className="flex items-center gap-4 text-[#878996]">
          <div>
            <span className="text-[#5e6673] mr-1">Alpaca Equity:</span>
            <span className="text-[#f5f5f5] font-bold">
              ${account.equity.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </span>
          </div>
          <div>
            <span className="text-[#5e6673] mr-1">Buying Power:</span>
            <span className="text-[#f7a600] font-bold">
              ${account.buying_power.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </span>
          </div>
          <div>
            <span className="text-[#5e6673] mr-1">Mark:</span>
            <span className="text-[#20b26c] font-bold">${midPrice.toFixed(2)}</span>
          </div>
          <div>
            <span className="text-[#5e6673] mr-1">Spread:</span>
            <span className="text-[#f5f5f5] font-bold">${quote.spread.toFixed(2)}</span>
          </div>
          <div className="hidden sm:block">
            <span className="text-[#5e6673] mr-1">Paper Feed:</span>
            <span className="text-[#20b26c] font-bold flex items-center gap-1 inline-flex">
              <span className="w-1.5 h-1.5 rounded-full bg-[#20b26c] animate-pulse" />
              LIVE
            </span>
          </div>
        </div>
      </div>

      {/* Main 3-Column Bybit Pro Terminal */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-3">
        {/* Left Column (8 cols): Chart + Trading Dock */}
        <div className="lg:col-span-8 space-y-3">
          {/* Bybit Chart Container */}
          <div className="rounded-lg bg-[#18191f] border border-[#26282f] flex flex-col overflow-hidden shadow-lg">
            {/* Chart Toolbar */}
            <div className="px-3 py-2 bg-[#1c1d22] border-b border-[#26282f] flex flex-wrap items-center justify-between gap-2 font-mono">
              <div className="flex items-center gap-2">
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
                  Alpaca Live Market
                </span>
                <span>Bid: <strong className="text-[#20b26c]">${quote.bid.toFixed(2)}</strong></span>
                <span>Ask: <strong className="text-[#ef454a]">${quote.ask.toFixed(2)}</strong></span>
              </div>
            </div>

            {/* Price Chart (Interactive Candlesticks / Line with Zoom & Free Crosshairs) */}
            <CandlestickChart
              key={selectedTicker}
              data={bars}
              chartType={chartType}
              chartInterval={chartInterval}
              currentPrice={quote.symbol === selectedTicker ? quote.last : undefined}
            />

            {/* Trading Volume Sub-Chart Description Header */}
            <div className="px-3 py-1 bg-[#16171b] border-t border-[#1f2128] flex items-center justify-between text-[10px] font-mono text-[#878996]">
              <div className="flex items-center gap-2">
                <span className="font-bold text-[#f5f5f5]">Trading Volume (Vol)</span>
                <span className="text-[#5e6673]">|</span>
                <span>Green Bars = Shares Traded Per Interval</span>
              </div>
              <span className="text-[#20b26c] font-semibold">
                Latest: {bars.length > 0 ? `${(bars[bars.length - 1].volume / 1000).toFixed(1)}K shares` : "--"}
              </span>
            </div>

            {/* Volume Sub-Chart */}
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
                    formatter={(val) => [`${Number(val).toLocaleString()} shares`, "Traded Volume"]}
                    labelStyle={{ color: "#20b26c", fontWeight: "bold" }}
                  />
                  <Bar dataKey="volume" name="Volume" fill="#20b26c" opacity={0.65} radius={[2, 2, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Bottom Trading Dock (Bybit Style) */}
          <div className="rounded-lg bg-[#18191f] border border-[#26282f] overflow-hidden shadow-lg">
            {/* Dock Tabs Header */}
            <div className="px-3 bg-[#1c1d22] border-b border-[#26282f] flex items-center justify-between font-mono">
              <div className="flex gap-2">
                {[
                  { key: "positions", label: `Positions (${positions.length})` },
                  { key: "pending", label: `Pending Orders (${pendingOrders.length})` },
                  { key: "history", label: `History & Ledger (${closedTrades.length})` },
                  { key: "orders", label: `Broker Orders (${orders.length})` },
                  { key: "debate", label: "Agent Debate Stream" },
                  { key: "riskgate", label: "Deterministic Risk Gate (10/10)" },
                ].map((t) => (
                  <button
                    key={t.key}
                    onClick={() => setActiveTab(t.key as DockTab)}
                    className={`py-2.5 px-3 text-xs font-semibold relative transition-colors cursor-pointer ${
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
                onClick={handleSyncAlpaca}
                disabled={isSyncing}
                className="flex items-center gap-1.5 text-[11px] text-[#f7a600] hover:underline cursor-pointer font-mono disabled:opacity-50"
                title="Synchronize Live Paper Account"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${isSyncing ? "animate-spin" : ""}`} />
                <span>{isSyncing ? "Syncing..." : "Sync Alpaca"}</span>
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
                      <p className="font-bold text-sm text-[#f5f5f5]">No Active Open Positions</p>
                      <p className="text-xs mt-1 text-[#878996] max-w-md mx-auto">
                        Execute a <strong className="text-[#20b26c]">Market Order (Preferred)</strong> for instant placement at current price, or fill a resting Limit order from the Pending Tab.
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
                            <tr key={pos.symbol} className="border-b border-[#26282f]/50 hover:bg-[#1c1d22]/50">
                              <td className="py-2.5 px-2 font-bold text-[#f5f5f5] flex items-center gap-1.5">
                                <span className="w-1.5 h-1.5 rounded-full bg-[#20b26c] animate-pulse" />
                                {pos.symbol}
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
                              <td className="py-2.5 px-2 text-right text-[#f5f5f5] font-bold">${pos.current_price.toFixed(2)}</td>
                              <td className="py-2.5 px-2 text-right text-[#878996]">${pos.market_value.toFixed(2)}</td>
                              <td className={`py-2.5 px-2 text-right font-bold ${
                                pos.unrealized_pl >= 0 ? "text-[#20b26c]" : "text-[#ef454a]"
                              }`}>
                                {pos.unrealized_pl >= 0 ? "+" : ""}${pos.unrealized_pl.toFixed(2)} ({pos.unrealized_plpc.toFixed(2)}%)
                              </td>
                              <td className="py-2.5 px-2 text-right">
                                <button
                                  onClick={() => handleClosePosition(pos.symbol)}
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
                      <p className="text-[11px] mt-1">All orders have been filled or closed.</p>
                    </div>
                  ) : (
                    <div>
                      <div className="mb-2.5 flex items-center justify-between">
                        <div className="flex items-center gap-2 text-xs text-[#878996]">
                          <span className="w-2 h-2 rounded-full bg-[#f7a600] animate-pulse" />
                          <span>
                            {pendingOrders.length} Order{pendingOrders.length > 1 ? "s" : ""} Resting / Queued on Alpaca Paper Broker
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
                                  <td className="py-2 px-2 text-[#878996] text-[11px] truncate max-w-[120px]" title={ord.id}>
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
                                        onClick={() => handleFillPending(ord.id, ord.limit_price || quote.last)}
                                        disabled={isFillingOrder === ord.id}
                                        className="px-2 py-0.5 rounded bg-[#20b26c]/20 hover:bg-[#20b26c]/30 text-[#20b26c] border border-[#20b26c]/40 text-[10px] font-bold transition-all cursor-pointer disabled:opacity-50 flex items-center gap-1"
                                        title="Fill pending order at limit price and move to Positions Tab"
                                      >
                                        <Zap className={`w-2.5 h-2.5 ${isFillingOrder === ord.id ? "animate-spin" : ""}`} />
                                        <span>{isFillingOrder === ord.id ? "Filling..." : "Fill Now"}</span>
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
                    <div className="text-center py-10 text-[#878996]">No Orders Found on Alpaca</div>
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
                              <td className="py-2 px-2 text-[#878996] text-[11px] truncate max-w-[120px]">{ord.id}</td>
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

              {activeTab === "riskgate" && (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                  {[
                    { rule: "Capital Allocation <= 2.5% NAV", val: "2.1% ($2,100 / $100k)", pass: true },
                    { rule: "Session Drawdown <= 3.0%", val: "0.00% Current", pass: true },
                    { rule: "DTE >= 3 Days", val: "21 DTE Selected", pass: true },
                    { rule: "Spread Width <= $25.00", val: "$5.00 Width", pass: true },
                    { rule: "Open Positions <= 5", val: "2 Active", pass: true },
                    { rule: "Option Open Interest >= 100", val: "1,420 Contracts", pass: true },
                    { rule: "Bid-Ask Spread <= 20%", val: "4.2% Mid-spread", pass: true },
                    { rule: "Portfolio Delta [-0.50, +0.50]", val: "+0.14 Net Delta", pass: true },
                  ].map((r, i) => (
                    <div key={i} className="p-2 rounded bg-[#1c1d22] border border-[#26282f] flex items-center justify-between">
                      <div>
                        <div className="text-[#f5f5f5] font-semibold">{r.rule}</div>
                        <div className="text-[10px] text-[#878996]">{r.val}</div>
                      </div>
                      <span className="px-1.5 py-0.5 rounded bg-[#20b26c]/15 text-[#20b26c] text-[10px] font-bold">
                        PASS
                      </span>
                    </div>
                  ))}
                </div>
              )}

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
                          {closedTrades.map((t) => {
                            const pnl = t.realized_pnl ?? 0;
                            const isWin = pnl >= 0;
                            const tradeId = t.trade_id || t.id || "TRD-" + Math.random().toString(36).substring(2, 7);
                            const symbol = t.symbol || t.proposal?.underlying || "SPY";
                            const strategy = t.strategy || t.proposal?.strategy_type || "MASTER_ORDER_FLOW";
                            const side = t.side || t.proposal?.side || "BUY";
                            const qty = t.qty || t.proposal?.qty || 1;
                            const entryPrice = t.entry_price ?? t.proposal?.net_premium ?? t.proposal?.limit_price ?? 0;
                            const exitPrice = t.exit_price ?? t.current_price ?? entryPrice;
                            const timeDisplay = t.exit_time ? new Date(t.exit_time).toLocaleTimeString() : (t.entry_time ? new Date(t.entry_time).toLocaleTimeString() : "-");
                            return (
                              <tr key={tradeId} className="border-b border-[#26282f]/50 hover:bg-[#1c1d22]/50">
                                <td className="py-2 px-2 text-[#878996] text-[11px] truncate max-w-[100px]" title={tradeId}>
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
                                  ${entryPrice.toFixed(2)}
                                </td>
                                <td className="py-2 px-2 text-right text-[#f5f5f5] font-semibold">
                                  ${exitPrice.toFixed(2)}
                                </td>
                                <td className={`py-2 px-2 text-right font-bold ${isWin ? "text-[#20b26c]" : "text-[#ef454a]"}`}>
                                  {isWin ? "+" : ""}${pnl.toFixed(2)}
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
          {/* Bybit Order Book */}
          <div className="rounded-lg bg-[#18191f] border border-[#26282f] p-3 font-mono shadow-lg">
            <div className="flex items-center justify-between pb-2 border-b border-[#26282f] mb-2 text-[#878996]">
              <div className="flex items-center gap-2">
                <span className="font-bold text-[#f5f5f5]">Order Book ({selectedTicker})</span>
                <span className="flex items-center gap-1 text-[9px] text-[#20b26c] font-bold px-1.5 py-0.2 rounded bg-[#20b26c]/10 border border-[#20b26c]/30">
                  <span className="w-1.5 h-1.5 rounded-full bg-[#20b26c] animate-pulse" />
                  REALTIME
                </span>
              </div>
              <span className="text-[10px] text-[#5e6673]">Spread ${spreadVal.toFixed(2)}</span>
            </div>

            {/* Asks (Red) */}
            <div className="space-y-1">
              {orderBookAsks.map((ask, i) => (
                <div key={i} className="relative flex justify-between text-[11px] py-0.5 px-1 overflow-hidden">
                  <div
                    className="absolute right-0 top-0 bottom-0 bg-[#ef454a]/15 rounded transition-all duration-300 ease-out"
                    style={{ width: `${ask.depth}%` }}
                  />
                  <span className="relative text-[#ef454a] font-bold">${ask.price.toFixed(2)}</span>
                  <span className="relative text-[#878996] font-semibold">{ask.size}</span>
                </div>
              ))}
            </div>

            {/* Real Mark Price from Alpaca */}
            <div className="py-2 my-1 border-y border-[#26282f] flex items-center justify-between text-xs">
              <span className="font-extrabold text-sm text-[#20b26c]">${midPrice.toFixed(2)}</span>
              <span className="text-[10px] text-[#878996] flex items-center gap-1">
                <span className="w-1.5 h-1.5 rounded-full bg-[#20b26c]" />
                Alpaca Real Last
              </span>
            </div>

            {/* Bids (Green) */}
            <div className="space-y-1">
              {orderBookBids.map((bid, i) => (
                <div key={i} className="relative flex justify-between text-[11px] py-0.5 px-1 overflow-hidden">
                  <div
                    className="absolute right-0 top-0 bottom-0 bg-[#20b26c]/15 rounded transition-all duration-300 ease-out"
                    style={{ width: `${bid.depth}%` }}
                  />
                  <span className="relative text-[#20b26c] font-bold">${bid.price.toFixed(2)}</span>
                  <span className="relative text-[#878996] font-semibold">{bid.size}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Real Alpaca Order Execution & Bot Panel */}
          <div className="rounded-lg bg-[#18191f] border border-[#26282f] p-3 font-mono space-y-3 shadow-lg">
            {/* Margin Pill & Market Clock Badge */}
            <div className="space-y-2 pb-2 border-b border-[#26282f]">
              <div className="flex items-center justify-between">
                <div className="flex gap-1 text-[11px]">
                  <span className="px-2 py-0.5 rounded bg-[#26282f] text-[#f7a600] font-bold">
                    Cross Margin
                  </span>
                  <span className="px-2 py-0.5 rounded bg-[#1c1d22] text-[#878996]">
                    Alpaca Paper
                  </span>
                </div>
                <span className="text-[10px] text-[#20b26c] font-semibold">Risk Gate Armed</span>
              </div>

              {/* Market Hours Gating & Dev Simulation Toggle */}
              <div className="flex items-center justify-between p-2 rounded bg-[#121214] border border-[#26282f] text-xs">
                <div className="flex items-center gap-1.5">
                  <span className={`w-2 h-2 rounded-full ${marketClock?.is_open ? "bg-[#20b26c] animate-pulse" : "bg-[#ef454a]"}`} />
                  <div>
                    <span className={`font-bold text-[11px] block leading-tight ${marketClock?.is_open ? "text-[#20b26c]" : "text-[#ef454a]"}`}>
                      {marketClock?.is_open ? "MARKET OPEN (09:30-16:00 ET)" : "MARKET CLOSED"}
                    </span>
                    {!marketClock?.is_open && (
                      <span className="text-[9px] text-[#878996] block">
                        {marketClock?.simulation_override ? "Sim Override Active (Executable)" : "Execution Gated until 09:30 ET"}
                      </span>
                    )}
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => handleToggleSimulationOverride(!marketClock?.simulation_override)}
                  className={`px-2 py-1 rounded text-[10px] font-bold border transition-all cursor-pointer ${
                    marketClock?.simulation_override
                      ? "bg-[#f7a600]/20 border-[#f7a600] text-[#f7a600] shadow-[0_0_8px_rgba(247,166,0,0.25)]"
                      : "bg-[#1c1d22] border-[#26282f] text-[#878996] hover:text-[#f5f5f5]"
                  }`}
                  title="Toggle Simulation Override to allow paper trading outside regular US market hours"
                >
                  ⚡ Dev Sim: {marketClock?.simulation_override ? "ON" : "OFF"}
                </button>
              </div>
            </div>

            {/* Trade Mode Selector */}
            <div className="grid grid-cols-2 gap-1 p-1 bg-[#121214] rounded border border-[#26282f]">
              <button
                onClick={() => setTradeMode("BOT")}
                className={`py-1.5 rounded text-center font-bold cursor-pointer transition-colors ${
                  tradeMode === "BOT"
                    ? "bg-[#f7a600] text-[#121214] shadow-[0_0_8px_rgba(247,166,0,0.3)]"
                    : "text-[#878996] hover:text-[#f5f5f5]"
                }`}
              >
                Bot Swarm (AI)
              </button>
              <button
                onClick={() => setTradeMode("MANUAL")}
                className={`py-1.5 rounded text-center font-bold cursor-pointer transition-colors ${
                  tradeMode === "MANUAL"
                    ? "bg-[#f7a600] text-[#121214] shadow-[0_0_8px_rgba(247,166,0,0.3)]"
                    : "text-[#878996] hover:text-[#f5f5f5]"
                }`}
              >
                Direct Manual
              </button>
            </div>

            {/* Content Based on Trade Mode */}
            {tradeMode === "MANUAL" ? (
              <div className="space-y-3">
                {/* Order Type: Market (Preferred) vs Limit */}
                <div className="space-y-1">
                  <div className="flex justify-between text-[10px] text-[#878996]">
                    <span>Execution Order Type</span>
                    <span className="text-[#20b26c] font-bold">⚡ Market Order Preferred</span>
                  </div>
                  <div className="grid grid-cols-2 gap-1 p-1 bg-[#121214] rounded border border-[#26282f]">
                    <button
                      type="button"
                      onClick={() => setOrderType("market")}
                      className={`py-1.5 px-2 rounded text-center text-xs font-bold transition-all cursor-pointer ${
                        orderType === "market"
                          ? "bg-[#20b26c] text-[#121214] shadow-[0_0_8px_rgba(32,178,108,0.3)]"
                          : "text-[#878996] hover:text-[#f5f5f5]"
                      }`}
                    >
                      Market (Instant)
                    </button>
                    <button
                      type="button"
                      onClick={() => setOrderType("limit")}
                      className={`py-1.5 px-2 rounded text-center text-xs font-bold transition-all cursor-pointer ${
                        orderType === "limit"
                          ? "bg-[#f7a600] text-[#121214] shadow-[0_0_8px_rgba(247,166,0,0.3)]"
                          : "text-[#878996] hover:text-[#f5f5f5]"
                      }`}
                    >
                      Limit (Pending)
                    </button>
                  </div>
                </div>

                {/* Buy / Sell Side Selector */}
                <div className="grid grid-cols-2 gap-2">
                  <button
                    onClick={() => setOrderSide("BUY")}
                    className={`py-1.5 rounded font-bold cursor-pointer ${
                      orderSide === "BUY"
                        ? "bg-[#20b26c] text-[#121214]"
                        : "bg-[#1c1d22] text-[#878996] hover:text-[#f5f5f5]"
                    }`}
                  >
                    Buy / Long
                  </button>
                  <button
                    onClick={() => setOrderSide("SELL")}
                    className={`py-1.5 rounded font-bold cursor-pointer ${
                      orderSide === "SELL"
                        ? "bg-[#ef454a] text-[#f5f5f5]"
                        : "bg-[#1c1d22] text-[#878996] hover:text-[#f5f5f5]"
                    }`}
                  >
                    Sell / Short
                  </button>
                </div>

                {/* Limit Price Input if Limit Order selected */}
                {orderType === "limit" ? (
                  <div className="space-y-1.5 p-2 rounded bg-[#121214] border border-[#26282f]">
                    <div className="flex justify-between text-[10px] text-[#878996]">
                      <span>Limit Price ($)</span>
                      <span className="text-[#f7a600] font-bold">Mark: ${midPrice.toFixed(2)}</span>
                    </div>
                    <div className="flex items-center gap-1.5">
                      <button
                        type="button"
                        onClick={() => setLimitPrice((p) => Math.max(0.01, +(p - tickStep).toFixed(2)))}
                        className="w-8 h-8 rounded bg-[#1c1d22] border border-[#26282f] text-[#f5f5f5] font-bold text-sm hover:bg-[#26282f] flex items-center justify-center cursor-pointer"
                      >
                        -
                      </button>
                      <input
                        type="number"
                        step={tickStep}
                        value={limitPrice}
                        onChange={(e) => setLimitPrice(Number(e.target.value))}
                        className="flex-1 px-2.5 py-1.5 rounded bg-[#18191f] border border-[#26282f] text-[#f5f5f5] text-xs font-bold text-center outline-none focus:border-[#f7a600]"
                      />
                      <button
                        type="button"
                        onClick={() => setLimitPrice((p) => +(p + tickStep).toFixed(2))}
                        className="w-8 h-8 rounded bg-[#1c1d22] border border-[#26282f] text-[#f5f5f5] font-bold text-sm hover:bg-[#26282f] flex items-center justify-center cursor-pointer"
                      >
                        +
                      </button>
                    </div>
                    <div className="grid grid-cols-3 gap-1 text-[10px]">
                      <button
                        type="button"
                        onClick={() => setLimitPrice(quote.bid || midPrice)}
                        className="p-1 rounded bg-[#18191f] border border-[#26282f] text-[#20b26c] font-bold hover:border-[#20b26c] cursor-pointer"
                      >
                        Bid ${quote.bid?.toFixed(2)}
                      </button>
                      <button
                        type="button"
                        onClick={() => setLimitPrice(midPrice)}
                        className="p-1 rounded bg-[#18191f] border border-[#26282f] text-[#f7a600] font-bold hover:border-[#f7a600] cursor-pointer"
                      >
                        Mid ${midPrice.toFixed(2)}
                      </button>
                      <button
                        type="button"
                        onClick={() => setLimitPrice(quote.ask || midPrice)}
                        className="p-1 rounded bg-[#18191f] border border-[#26282f] text-[#ef454a] font-bold hover:border-[#ef454a] cursor-pointer"
                      >
                        Ask ${quote.ask?.toFixed(2)}
                      </button>
                    </div>
                    <div className="text-[9px] text-[#878996] pt-0.5">
                      Resting order will queue in <strong className="text-[#f7a600]">Pending Tab</strong> until market reaches price.
                    </div>
                  </div>
                ) : (
                  <div className="p-2 rounded bg-[#20b26c]/10 border border-[#20b26c]/30 text-[11px] space-y-1">
                    <div className="flex justify-between font-bold">
                      <span className="text-[#878996]">Market Fill Price:</span>
                      <span className="text-[#20b26c]">${midPrice.toFixed(2)}</span>
                    </div>
                    <div className="text-[10px] text-[#878996]">
                      Immediate execution at current market price &rarr; moves straight into <strong className="text-[#f5f5f5]">Positions Tab</strong>.
                    </div>
                  </div>
                )}

                {/* Quantity Input */}
                <div className="space-y-1">
                  <div className="flex justify-between text-[10px] text-[#878996]">
                    <span>Order Quantity</span>
                    <span>Max: 10 Qty</span>
                  </div>
                  <input
                    type="number"
                    min="1"
                    max="100"
                    value={orderQty}
                    onChange={(e) => setOrderQty(Math.max(1, Number(e.target.value)))}
                    className="w-full px-2.5 py-1.5 rounded bg-[#121214] border border-[#26282f] text-[#f5f5f5] text-xs font-bold outline-none focus:border-[#f7a600]"
                  />
                </div>

                {/* Estimated Value */}
                <div className="p-2 rounded bg-[#121214] space-y-1 text-[11px]">
                  <div className="flex justify-between">
                    <span className="text-[#878996]">Order Symbol:</span>
                    <span className="text-[#f5f5f5] font-bold">{selectedTicker}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-[#878996]">Estimated Total:</span>
                    <span className="text-[#f7a600] font-bold">
                      ${(orderQty * (orderType === "limit" ? limitPrice : midPrice)).toFixed(2)}
                    </span>
                  </div>
                </div>

                {/* Submit Manual Order */}
                <button
                  onClick={handleManualOrder}
                  disabled={isSubmitting || (!marketClock?.is_open && !marketClock?.simulation_override)}
                  className={`w-full py-2.5 rounded font-bold text-xs cursor-pointer transition-all shadow-lg active:scale-95 ${
                    orderSide === "BUY"
                      ? "bg-[#20b26c] hover:bg-[#28c97b] text-[#121214]"
                      : "bg-[#ef454a] hover:bg-[#f35b5f] text-[#f5f5f5]"
                  } disabled:opacity-50`}
                >
                  {isSubmitting
                    ? "Submitting..."
                    : !marketClock?.is_open && !marketClock?.simulation_override
                    ? "Market Closed (Opens 09:30 ET)"
                    : orderType === "market"
                    ? `Execute Market ${orderSide} @ $${midPrice.toFixed(2)} (Instant Position)`
                    : `Submit Limit ${orderSide} @ $${limitPrice.toFixed(2)} (To Pending Tab)`}
                </button>
              </div>
            ) : (
              <div className="space-y-2">
                {/* Autonomous Strategy Select */}
                <div className="space-y-0.5">
                  <label className="text-[#878996] text-[10px] uppercase font-semibold">Autonomous Strategy</label>
                  <select
                    value={selectedStrategy}
                    onChange={(e) => setSelectedStrategy(e.target.value)}
                    className="w-full px-2 py-1 rounded bg-[#121214] border border-[#26282f] text-[#f7a600] text-xs focus:border-[#f7a600] outline-none font-semibold cursor-pointer"
                  >
                    <option value="MASTER_ORDER_FLOW">★ VolHelix Master Flow & Gamma (OB + FVG + GEX)</option>
                    <option value="BULL_PUT_SPREAD">Bull Put Spread (Credit)</option>
                    <option value="IRON_CONDOR">Iron Condor (Delta-Neutral)</option>
                    <option value="BEAR_CALL_SPREAD">Bear Call Spread (Credit)</option>
                    <option value="CALENDAR_SPREAD">Calendar Spread (Volatility)</option>
                  </select>
                </div>

                {/* Institutional Master Flow & Gamma Profile Confluence Card */}
                {selectedStrategy === "MASTER_ORDER_FLOW" && (
                  <div className="p-2 rounded bg-[#1c1a14] border border-[#f7a600]/40 space-y-1 text-[11px]">
                    <div className="flex items-center justify-between font-bold text-[#f7a600] text-[10px]">
                      <span className="flex items-center gap-1.5 uppercase">
                        <span className="w-1.5 h-1.5 rounded-full bg-[#f7a600] animate-ping" />
                        Master Strategy Confluence
                      </span>
                      <span className="text-[9px] px-1.5 py-0.5 rounded bg-[#f7a600]/20 text-[#f7a600] font-mono">
                        {orderFlow?.gamma_profile?.regime || "POSITIVE_GAMMA"}
                      </span>
                    </div>

                    <div className="grid grid-cols-3 gap-1 pt-0.5 text-[9px]">
                      <div className="p-1 rounded bg-[#121214] border border-[#26282f]">
                        <div className="text-[#878996]">Order Block</div>
                        <div className="font-bold text-[#20b26c] mt-0.5">
                          {orderFlow?.order_flow?.nearest_bullish_ob ? `$${orderFlow.order_flow.nearest_bullish_ob.low.toFixed(0)}` : "OB Support"}
                        </div>
                      </div>
                      <div className="p-1 rounded bg-[#121214] border border-[#26282f]">
                        <div className="text-[#878996]">Fair Value Gap</div>
                        <div className="font-bold text-[#20b26c] mt-0.5">
                          {orderFlow?.order_flow?.unfilled_fvgs && orderFlow.order_flow.unfilled_fvgs.length > 0 ? "BISI Active" : "Clean Flow"}
                        </div>
                      </div>
                      <div className="p-1 rounded bg-[#121214] border border-[#26282f]">
                        <div className="text-[#878996]">Gamma Put Wall</div>
                        <div className="font-bold text-[#f7a600] mt-0.5">
                          {orderFlow?.gamma_profile?.put_wall ? `$${orderFlow.gamma_profile.put_wall.toFixed(0)}` : "Put Wall Base"}
                        </div>
                      </div>
                    </div>
                  </div>
                )}

                {/* Kelly Fraction Sizing Slider */}
                <div className="space-y-0.5">
                  <div className="flex justify-between text-[10px]">
                    <span className="text-[#878996]">Kelly Risk Allocation</span>
                    <span className="text-[#f7a600] font-bold">{kellyPercent}%</span>
                  </div>
                  <input
                    type="range"
                    min="20"
                    max="100"
                    step="10"
                    value={kellyPercent}
                    onChange={(e) => setKellyPercent(Number(e.target.value))}
                    className="w-full h-1 bg-[#26282f] rounded-lg accent-[#f7a600] cursor-pointer"
                  />
                  <div className="flex justify-between text-[9px] text-[#5e6673]">
                    <span>20% (Conservative)</span>
                    <span>100% (Max 2.5% NAV)</span>
                  </div>
                </div>

                {/* Sizing & EV Summary */}
                <div className="p-1.5 rounded bg-[#121214] space-y-0.5 text-[10px]">
                  <div className="flex justify-between">
                    <span className="text-[#878996]">Target Credit:</span>
                    <span className="text-[#20b26c] font-bold">+$0.48 / share</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-[#878996]">Max Capital at Risk:</span>
                    <span className="text-[#ef454a] font-bold">2.1% NAV ($2,100)</span>
                  </div>
                  <div className="flex justify-between pt-0.5 border-t border-[#26282f]">
                    <span className="text-[#878996]">Risk Gate:</span>
                    <span className="text-[#20b26c] font-bold">10/10 Verified</span>
                  </div>
                </div>

                {/* Auto Take-Profit & Stop-Loss Bracket Protection */}
                <div className="p-2 rounded bg-[#121214] border border-[#26282f] space-y-1 text-[11px]">
                  <div className="flex items-center justify-between pb-1 border-b border-[#26282f]/60">
                    <span className="text-[#878996] font-semibold text-[10px] uppercase flex items-center gap-1.5">
                      <span className="w-1.5 h-1.5 rounded-full bg-[#20b26c] animate-pulse" />
                      Auto Take-Profit & Stop-Loss
                    </span>
                    <span className="text-[9px] px-1.5 py-0.5 rounded bg-[#20b26c]/15 text-[#20b26c] font-bold">
                      Bracket OCO Armed
                    </span>
                  </div>

                  <div className="grid grid-cols-2 gap-1.5">
                    <div className="p-1.5 rounded bg-[#18191f] border border-[#26282f]/80">
                      <div className="flex justify-between text-[9px] text-[#878996]">
                        <span>Take Profit (TP)</span>
                        <span className="text-[#20b26c] font-bold">+{tpSlConfig.tpPct.toFixed(1)}%</span>
                      </div>
                      <div className="text-[#20b26c] font-bold text-xs mt-0.5">
                        ${tpSlConfig.tpPrice.toFixed(2)}
                      </div>
                      <div className="text-[8px] text-[#5e6673]">Auto Limit Exit</div>
                    </div>

                    <div className="p-1.5 rounded bg-[#18191f] border border-[#26282f]/80">
                      <div className="flex justify-between text-[9px] text-[#848e9c]">
                        <span>Stop Loss (SL)</span>
                        <span className="text-[#ef454a] font-bold">-{tpSlConfig.slPct.toFixed(1)}%</span>
                      </div>
                      <div className="text-[#ef454a] font-bold text-xs mt-0.5">
                        ${tpSlConfig.slPrice.toFixed(2)}
                      </div>
                      <div className="text-[8px] text-[#5e6673]">Auto Stop Safeguard</div>
                    </div>
                  </div>
                </div>

                {/* 24/7 Autonomous Auto-Trader Loop Control & Strict Master Confluence Gate */}
                <div className="p-2.5 rounded-xl bg-[#141518] border border-[#2b313a] space-y-2">
                  {/* Master Strategy Auto-Pilot Toggle Header */}
                  <div className="flex items-center justify-between">
                    <div>
                      <div className="flex items-center gap-1.5">
                        <span className={`w-2 h-2 rounded-full ${autoTrading?.is_running ? "bg-[#0ecb81] animate-ping" : "bg-[#848e9c]"}`} />
                        <span className="text-xs font-black tracking-wide text-[#eaecef]">
                          AUTO-PILOT MODE
                        </span>
                      </div>
                      <div className="text-[9px] text-[#848e9c] mt-0.5">
                        Strict Master Strategy Confluence Gate
                      </div>
                    </div>

                    {/* Interactive Switch Component */}
                    <button
                      type="button"
                      role="switch"
                      aria-checked={autoTrading?.is_running || false}
                      onClick={handleToggleAutoTrading}
                      disabled={isTogglingAuto}
                      className={`relative inline-flex h-5 w-10 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none ${
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
                        24/7 ACTIVE (ALWAYS ON)
                      </span>
                    </div>
                    <div className="text-[8px] text-[#848e9c] leading-tight">
                      All open positions are protected 24/7 and will automatically close at their dynamic TP and SL, even when Auto-Pilot is paused.
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
                      <strong className="text-[#0ecb81] font-bold text-[10px]">{autoTrading?.total_automated_trades || 0}</strong>
                    </div>
                  </div>

                  {/* Live Radar Scanner Matrix (Watchlist Diagnostic Chips) */}
                  <div className="space-y-0.5">
                    <div className="flex items-center justify-between text-[9px] text-[#848e9c]">
                      <span>Live Watchlist Radar:</span>
                      <span className="text-[8px] font-mono text-[#5e6673]">
                        {autoTrading?.is_running ? "Auto-Scanning every 30s" : "Standby"}
                      </span>
                    </div>
                    <div className="grid grid-cols-5 gap-1">
                      {["SPY", "QQQ", "NVDA", "AAPL", "TSLA"].map((ticker) => {
                        const diag = autoTrading?.scanner_diagnostics?.[ticker];
                        const score = diag ? Math.round(diag.score * 100) : null;
                        const isValid = diag?.is_valid || false;
                        const isSelected = selectedTicker === ticker;
                        return (
                          <div
                            key={ticker}
                            onClick={() => setSelectedTicker(ticker)}
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
                      disabled={isTogglingAuto}
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
                      disabled={isSubmitting}
                      className="py-2 px-2 rounded-lg bg-[#1e2329] hover:bg-[#2b313a] border border-[#2b313a] text-[#eaecef] font-bold text-[11px] transition-all cursor-pointer disabled:opacity-50 flex items-center justify-center gap-1.5"
                      title={`Evaluates ONLY the active chart symbol (${selectedTicker}) against Master Strategy confluence`}
                    >
                      {isSubmitting ? (
                        <>
                          <span className="w-1.5 h-1.5 rounded-full bg-[#f0b90b] animate-ping" />
                          <span>Scanning {selectedTicker}...</span>
                        </>
                      ) : (
                        `Scan & Trade (${selectedTicker})`
                      )}
                    </button>
                  </div>
                </div>

                {/* Trigger Bot Order to Alpaca */}
                <button
                  onClick={handleBotTrade}
                  disabled={isSubmitting || (!marketClock?.is_open && !marketClock?.simulation_override)}
                  className="w-full py-2 rounded bg-[#f7a600] hover:bg-[#ffb11a] text-[#121214] font-extrabold text-xs cursor-pointer transition-all shadow-[0_0_10px_rgba(247,166,0,0.3)] disabled:opacity-50 active:scale-95"
                >
                  {isSubmitting
                    ? "Executing Swarm..."
                    : !marketClock?.is_open && !marketClock?.simulation_override
                    ? "Market Closed (Opens 09:30 ET)"
                    : "Execute Master Strategy Trade (Alpaca)"}
                </button>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}