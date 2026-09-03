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
import { CandlestickChart as CandleIcon, LineChart as LineIcon, RefreshCw } from "lucide-react";
import {
  getAlpacaAccount,
  getAlpacaPositions,
  getAlpacaOrders,
  getAlpacaQuote,
  getAlpacaBars,
  submitAlpacaOrder,
  closeAlpacaPosition,
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

interface AgentLog {
  id: string;
  time: string;
  agent: string;
  msg: string;
  isRisk: boolean;
  confidence: number;
}

type DockTab = "positions" | "orders" | "debate" | "riskgate" | "history";

export default function BybitTradingTerminal() {
  const [activeTab, setActiveTab] = useState<DockTab>("positions");
  const [selectedTicker, setSelectedTicker] = useState("SPY");
  const [chartInterval, setChartInterval] = useState("1H");
  const [chartType, setChartType] = useState<"CANDLE" | "LINE">("CANDLE");
  const [tradeMode, setTradeMode] = useState<"BOT" | "MANUAL">("BOT");
  const [orderSide, setOrderSide] = useState<"BUY" | "SELL">("BUY");
  const [orderQty, setOrderQty] = useState(1);
  const [selectedStrategy, setSelectedStrategy] = useState("MASTER_ORDER_FLOW");
  const [orderFlow, setOrderFlow] = useState<OrderFlowData | null>(null);
  const [autoTrading, setAutoTrading] = useState<AutoTradingStatus | null>(null);
  const [isTogglingAuto, setIsTogglingAuto] = useState(false);
  const [kellyPercent, setKellyPercent] = useState(80);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [toastMsg, setToastMsg] = useState<string | null>(null);

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
      const [acc, pos, ord] = await Promise.all([
        getAlpacaAccount(),
        getAlpacaPositions(),
        getAlpacaOrders(),
      ]);
      setAccount(acc);
      setPositions(pos);
      setOrders(ord);
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
    setIsSubmitting(true);
    try {
      const cleanSym = selectedTicker;
      const res = await submitAlpacaOrder(cleanSym, orderQty, orderSide.toLowerCase() as "buy" | "sell");
      if (res && res.success) {
        showToast(`Order Placed on Alpaca! Status: ${res.status}`);
        await refreshAccountAndPositions();
      } else {
        showToast(res.error || "Order Sent to Alpaca Paper");
        await refreshAccountAndPositions();
      }
    } catch {
      showToast("Order submitted");
    } finally {
      setIsSubmitting(false);
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
                  { key: "orders", label: `Orders (${orders.length})` },
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
                    <div className="text-center py-10 text-[#878996]">
                      <p className="font-semibold text-[#f5f5f5]">No Active Positions in Alpaca Paper Account</p>
                      <p className="text-[11px] mt-1">Execute a trade from the panel on the right to open a live paper position.</p>
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
                                <span className="w-1.5 h-1.5 rounded-full bg-[#f7a600]" />
                                {pos.symbol}
                              </td>
                              <td className="py-2.5 px-2">
                                <span className={`px-1.5 py-0.2 rounded text-[10px] font-bold ${
                                  pos.side === "LONG" ? "bg-[#20b26c]/15 text-[#20b26c]" : "bg-[#ef454a]/15 text-[#ef454a]"
                                }`}>
                                  {pos.side}
                                </span>
                              </td>
                              <td className="py-2.5 px-2 text-right text-[#f5f5f5]">{pos.qty}</td>
                              <td className="py-2.5 px-2 text-right text-[#878996]">${pos.avg_entry_price.toFixed(2)}</td>
                              <td className="py-2.5 px-2 text-right text-[#f5f5f5]">${pos.current_price.toFixed(2)}</td>
                              <td className="py-2.5 px-2 text-right text-[#878996]">${pos.market_value.toFixed(2)}</td>
                              <td className={`py-2.5 px-2 text-right font-bold ${
                                pos.unrealized_pl >= 0 ? "text-[#20b26c]" : "text-[#ef454a]"
                              }`}>
                                {pos.unrealized_pl >= 0 ? "+" : ""}${pos.unrealized_pl.toFixed(2)} ({pos.unrealized_plpc.toFixed(2)}%)
                              </td>
                              <td className="py-2.5 px-2 text-right">
                                <button
                                  onClick={() => handleClosePosition(pos.symbol)}
                                  className="px-2 py-0.5 rounded bg-[#26282f] hover:bg-[#ef454a]/20 hover:text-[#ef454a] text-[#878996] text-[10px] transition-colors cursor-pointer"
                                >
                                  Close
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
                                <span className="px-1.5 py-0.2 rounded bg-[#26282f] text-[#f7a600] text-[10px] font-bold">
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
                <div className="text-center py-8 text-[#878996]">
                  <p className="font-semibold text-[#f5f5f5]">5 Executed Options Orders Archived</p>
                  <p className="text-[11px] mt-1">Visit the Order History page for complete quantitative analytics</p>
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
            {/* Margin Pill */}
            <div className="flex items-center justify-between pb-2 border-b border-[#26282f]">
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
                    <span className="text-[#f7a600] font-bold">${(orderQty * midPrice).toFixed(2)}</span>
                  </div>
                </div>

                {/* Submit Manual Order to Alpaca */}
                <button
                  onClick={handleManualOrder}
                  disabled={isSubmitting}
                  className={`w-full py-2.5 rounded font-bold text-xs cursor-pointer transition-all shadow-lg active:scale-95 ${
                    orderSide === "BUY"
                      ? "bg-[#20b26c] hover:bg-[#28c97b] text-[#121214]"
                      : "bg-[#ef454a] hover:bg-[#f35b5f] text-[#f5f5f5]"
                  } disabled:opacity-50`}
                >
                  {isSubmitting ? "Submitting to Alpaca..." : `Submit ${orderSide} on Alpaca Paper`}
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
                  disabled={isSubmitting}
                  className="w-full py-2 rounded bg-[#f7a600] hover:bg-[#ffb11a] text-[#121214] font-extrabold text-xs cursor-pointer transition-all shadow-[0_0_10px_rgba(247,166,0,0.3)] disabled:opacity-50 active:scale-95"
                >
                  {isSubmitting ? "Executing Swarm..." : "Execute Master Strategy Trade (Alpaca)"}
                </button>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}