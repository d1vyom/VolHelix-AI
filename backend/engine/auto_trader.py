import time
import threading
import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import List, Optional, Dict

from backend.config import settings
from backend.models.market import StrategyType, TradeStatus
from backend.models.trade import TradeProposal, TradeRecord
from backend.store.trade_log import trade_log
from backend.mcp.client import BinanceClient
from backend.engine.order_flow import (
    analyze_order_flow,
    calculate_master_strategy_tp_sl,
    evaluate_master_strategy_setup
)
from backend.utils.logger import get_logger

logger = get_logger("auto_trader")


class AutoTrader:
    """
    Autonomous Background Trading Daemon for 24/7 Crypto Spot Trading.
    Continuously scans market structure (Order Blocks, Fair Value Gaps, Liquidity Heatmap),
    evaluates Master Strategy confluence (Score >= 0.70), automatically calculates dynamic TP and SL,
    and dispatches paper orders on Binance Spot Testnet with 24/7 Position Guardian protection.
    """
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(AutoTrader, cls).__new__(cls, *args, **kwargs)
        return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return
        self._initialized = True
        self.is_running: bool = False
        self.interval_seconds: int = 30
        self.max_open_positions: int = 5
        self.watched_symbols: List[str] = list(settings.WATCHED_SYMBOLS)
        self.total_automated_trades: int = 0
        self.last_run_timestamp: Optional[str] = None
        self.last_trade_result: Optional[Dict] = None
        self.last_log: str = "Auto-trader initialized (Standby)"
        self.scanner_diagnostics: Dict[str, Dict] = {}
        self._stop_event: threading.Event = threading.Event()
        self._worker_thread: Optional[threading.Thread] = None
        self._binance_client: Optional[BinanceClient] = None

        # 24/7 Position Guardian & TP/SL Manager: Runs continuously even if Auto-Pilot is OFF
        self.guardian_interval_seconds: int = 5
        self._guardian_thread: Optional[threading.Thread] = None
        self._guardian_stop_event: threading.Event = threading.Event()
        self.ensure_guardian_running()

    def _get_binance_client(self) -> BinanceClient:
        if self._binance_client is None:
            self._binance_client = BinanceClient()
        return self._binance_client

    # Backward compatibility alias
    def _get_trading_client(self) -> BinanceClient:
        return self._get_binance_client()

    def _get_stock_client(self) -> BinanceClient:
        return self._get_binance_client()

    def ensure_guardian_running(self):
        """Ensures the 24/7 Position Guardian thread is active."""
        if self._guardian_thread is None or not self._guardian_thread.is_alive():
            self._guardian_stop_event.clear()
            self._guardian_thread = threading.Thread(target=self._guardian_loop, daemon=True)
            self._guardian_thread.start()

    def _guardian_loop(self):
        """
        24/7 Background Guardian Loop.
        Monitors active positions, evaluates dynamic TP and SL thresholds, and automatically
        closes positions when TP or SL is breached, EVEN IF AUTO-PILOT IS TURNED OFF!
        """
        logger.info("Position Guardian & TP/SL Manager active (24/7 Crypto Protection).")
        while not self._guardian_stop_event.is_set():
            try:
                self._check_and_manage_positions()
            except Exception as e:
                logger.error(f"Error in Position Guardian cycle: {e}")
            if self._guardian_stop_event.wait(timeout=self.guardian_interval_seconds):
                break

    def _check_and_manage_positions(self):
        """
        Continuous Position Guardian & TP/SL Manager.
        Runs 24/7 independently of Auto-Pilot state.
        Monitors active positions, evaluates dynamic TP and SL thresholds,
        and automatically closes positions when TP or SL is reached.
        """
        client = self._get_binance_client()
        try:
            positions = client.get_positions()
            pos_by_sym = {p["symbol"]: p for p in positions}
        except Exception as e:
            logger.debug(f"Position Guardian failed to query Binance positions: {e}")
            return

        try:
            open_trades = asyncio.run(trade_log.get_open_trades())
        except Exception as e:
            logger.debug(f"Position Guardian failed to fetch open trades from DB: {e}")
            return

        for trade in open_trades:
            sym = trade.proposal.symbol or trade.proposal.underlying
            tp_price = trade.take_profit_price or getattr(trade.proposal, "take_profit", None)
            sl_price = trade.stop_loss_price or getattr(trade.proposal, "stop_loss", None)
            entry_price = trade.entry_price or trade.proposal.entry_price or (trade.proposal.breakevens[0] if trade.proposal.breakevens else 0.0)

            # Get current price
            current_price = 0.0
            if sym in pos_by_sym:
                current_price = pos_by_sym[sym]["current_price"]
                qty = pos_by_sym[sym]["qty"]
            else:
                p_data = client.get_price(sym)
                current_price = p_data.get("price", entry_price)
                qty = trade.proposal.qty or 0.001

            if current_price <= 0:
                current_price = entry_price

            # Case A: Position is active on Binance
            if sym in pos_by_sym:
                # Check Take Profit
                if tp_price and tp_price > 0 and current_price >= tp_price:
                    logger.info(f"Target reached for {sym}! Current: ${current_price:.2f} >= TP: ${tp_price:.2f}. Executing Take Profit.")
                    self._close_position_and_finalize_trade(
                        client=client,
                        trade=trade,
                        symbol=sym,
                        exit_price=current_price,
                        entry_price=entry_price,
                        qty=qty,
                        exit_type="TAKE_PROFIT",
                        reason=f"Take Profit Target Reached: Current ${current_price:.2f} >= TP ${tp_price:.2f}"
                    )
                    continue

                # Check Stop Loss
                if sl_price and sl_price > 0 and current_price <= sl_price:
                    logger.info(f"Stop breached for {sym}! Current: ${current_price:.2f} <= SL: ${sl_price:.2f}. Executing Stop Loss.")
                    self._close_position_and_finalize_trade(
                        client=client,
                        trade=trade,
                        symbol=sym,
                        exit_price=current_price,
                        entry_price=entry_price,
                        qty=qty,
                        exit_type="STOP_LOSS",
                        reason=f"Stop Loss Protection Triggered: Current ${current_price:.2f} <= SL ${sl_price:.2f}"
                    )
                    continue

            else:
                # Case B: Trade recorded in DB but position not in wallet (e.g. manually sold or stopped)
                entry_time_str = trade.entry_time or ""
                time_elapsed = 999
                if entry_time_str:
                    try:
                        time_elapsed = (datetime.now() - datetime.fromisoformat(entry_time_str)).total_seconds()
                    except Exception:
                        time_elapsed = 999

                if time_elapsed > 30:
                    realized_pnl = round((current_price - entry_price) * qty, 2)
                    exit_type = "TAKE_PROFIT" if (tp_price and current_price >= tp_price * 0.99) else "STOP_LOSS"
                    trade.status = TradeStatus.CLOSED
                    trade.realized_pnl = realized_pnl
                    trade.exit_time = datetime.now().isoformat()
                    trade.exit_price = current_price
                    asyncio.run(trade_log.save_trade(trade))

                    msg = f"Position {sym} synchronized with wallet. Exit: ${current_price:.2f} | Realized PnL: ${realized_pnl:+.2f}"
                    logger.info(msg)
                    self._emit_guardian_event(exit_type, sym, current_price, realized_pnl, msg)

        # Check and fill pending limit orders when market price reaches limit
        try:
            pending_trades = asyncio.run(trade_log.get_pending_trades())
            for ptrade in pending_trades:
                sym = ptrade.proposal.symbol or ptrade.proposal.underlying
                limit_p = ptrade.proposal.limit_price or (ptrade.proposal.breakevens[0] if ptrade.proposal.breakevens else None)
                if not limit_p:
                    continue

                p_info = client.get_price(sym)
                cur_price = p_info.get("price", 0.0)
                if cur_price <= 0:
                    continue

                side = (ptrade.proposal.side or "BUY").upper()
                should_fill = False
                if side == "BUY" and cur_price <= limit_p:
                    should_fill = True
                elif side == "SELL" and cur_price >= limit_p:
                    should_fill = True

                if should_fill:
                    asyncio.run(trade_log.fill_pending_trade(ptrade.trade_id, fill_price=cur_price))
                    msg = f"LIMIT FILLED: {sym} limit order {ptrade.trade_id[:8]} filled at ${cur_price:.2f} (Limit: ${limit_p:.2f}). Moved to Positions Tab."
                    logger.info(msg)
                    self._emit_fill_event(ptrade.trade_id, sym, cur_price, msg)
        except Exception as e:
            logger.debug(f"Position Guardian pending limit check error: {e}")

    def _close_position_and_finalize_trade(
        self,
        client: BinanceClient,
        trade: TradeRecord,
        symbol: str,
        exit_price: float,
        entry_price: float,
        qty: float,
        exit_type: str,
        reason: str
    ):
        """Closes crypto spot position by selling held asset on testnet and updates DB."""
        try:
            # 1. Cancel open orders for this pair
            client.cancel_all_orders(symbol)
            time.sleep(0.3)

            # 2. Sell held quantity on testnet
            if qty > 0:
                client.place_order(
                    symbol=symbol,
                    side="SELL",
                    order_type="MARKET",
                    quantity=qty
                )
        except Exception as e:
            logger.warning(f"Error executing position close for {symbol}: {e}")

        realized_pnl = round((exit_price - entry_price) * qty, 2)
        trade.status = TradeStatus.CLOSED
        trade.realized_pnl = realized_pnl
        trade.exit_time = datetime.now().isoformat()
        trade.exit_price = exit_price
        asyncio.run(trade_log.save_trade(trade))

        msg = f"AUTO-EXIT [{exit_type}]: {symbol} closed at ${exit_price:.2f}. Realized PnL: ${realized_pnl:+.2f}. {reason}"
        logger.info(msg)
        self._emit_guardian_event(exit_type, symbol, exit_price, realized_pnl, msg)

    def _emit_guardian_event(self, exit_type: str, symbol: str, price: float, pnl: float, message: str):
        try:
            from backend.api.websocket import sio
            async def _emit():
                await sio.emit("reasoning_event", {
                    "agent": "RiskGate",
                    "message": message,
                    "confidence": 1.0
                })
                await sio.emit("trade_executed", {
                    "trade_id": symbol,
                    "status": "CLOSED",
                    "realized_pnl": pnl,
                    "exit_price": price
                })
            threading.Thread(target=lambda: asyncio.run(_emit()), daemon=True).start()
        except Exception:
            pass

    def _emit_fill_event(self, trade_id: str, symbol: str, price: float, message: str):
        try:
            from backend.api.websocket import sio
            async def _emit():
                await sio.emit("reasoning_event", {
                    "agent": "AutoTrader",
                    "message": message,
                    "confidence": 1.0
                })
                await sio.emit("trade_filled", {
                    "trade_id": trade_id,
                    "symbol": symbol,
                    "fill_price": price,
                    "status": "OPEN"
                })
            threading.Thread(target=lambda: asyncio.run(_emit()), daemon=True).start()
        except Exception:
            pass

    def start(self, interval: int = 30) -> Dict:
        """Start the background autonomous trading loop."""
        self.ensure_guardian_running()
        if self.is_running:
            return {"success": True, "message": "Auto-trader is already running", "status": self.status()}

        self.interval_seconds = max(10, interval)
        self._stop_event.clear()
        self.is_running = True
        self.last_log = f"Autonomous loop started. Scanning every {self.interval_seconds}s across crypto pairs."
        logger.info(self.last_log)

        self._worker_thread = threading.Thread(target=self._loop, daemon=True)
        self._worker_thread.start()
        return {"success": True, "message": "Auto-trader started successfully", "status": self.status()}

    def stop(self) -> Dict:
        """Stop the background autonomous trading loop (Guardian remains active for TP/SL)."""
        if not self.is_running:
            return {"success": True, "message": "Auto-trader is already stopped", "status": self.status()}

        self._stop_event.set()
        self.is_running = False
        if self._worker_thread and self._worker_thread.is_alive() and threading.current_thread() != self._worker_thread:
            self._worker_thread.join(timeout=3.0)
        self.last_log = "Autonomous scanning paused by operator. Position Guardian active 24/7 for TP/SL."
        logger.info(self.last_log)
        return {"success": True, "message": "Auto-trader stopped successfully", "status": self.status()}

    def status(self) -> Dict:
        """Return live autonomous status, guardian state, and trade statistics."""
        return {
            "is_running": self.is_running,
            "interval_seconds": self.interval_seconds,
            "max_open_positions": self.max_open_positions,
            "watched_symbols": self.watched_symbols,
            "total_automated_trades": self.total_automated_trades,
            "last_run_timestamp": self.last_run_timestamp,
            "last_trade_result": self.last_trade_result,
            "last_log": self.last_log,
            "scanner_diagnostics": self.scanner_diagnostics,
            "guardian_active": self._guardian_thread is not None and self._guardian_thread.is_alive()
        }

    def trigger_cycle(self, symbol: Optional[str] = None) -> Dict:
        """
        Manually trigger an automated execution scan cycle immediately.
        If symbol is provided, scans ONLY that active chart symbol.
        """
        self.ensure_guardian_running()
        clean_sym = symbol.strip().upper() if symbol else None
        if clean_sym:
            logger.info(f"Manual trigger of autonomous trading cycle requested for symbol: {clean_sym}")
        else:
            logger.info("Manual trigger of autonomous trading cycle requested across crypto watchlist.")
        return self._execute_scan_cycle(requested_symbol=clean_sym)

    def _loop(self):
        """Worker thread main execution loop."""
        try:
            self._execute_scan_cycle()
        except Exception as e:
            logger.error(f"Error in initial auto-trade cycle: {e}")

        while not self._stop_event.is_set():
            if self._stop_event.wait(timeout=self.interval_seconds):
                break
            try:
                self._execute_scan_cycle()
            except Exception as e:
                logger.error(f"Error in autonomous trading loop: {e}")

    def _execute_scan_cycle(self, requested_symbol: Optional[str] = None) -> Dict:
        """
        Scans symbols against the Master Strategy Confluence Gate (Score >= 0.70).
        Evaluates Order Blocks, Fair Value Gaps, and Liquidity Heatmaps from Binance.
        """
        self.last_run_timestamp = datetime.now().isoformat()
        if not requested_symbol and self._stop_event.is_set():
            return {"success": True, "executed": False, "reason": "Stopped", "scanner_diagnostics": self.scanner_diagnostics}

        client = self._get_binance_client()

        # 1. Check open positions limit (active trades tracked in trade_log)
        try:
            open_trades = asyncio.run(trade_log.get_open_trades())
            active_symbols = {t.proposal.symbol or t.proposal.underlying for t in open_trades if t.status == TradeStatus.OPEN}
            if len(open_trades) >= self.max_open_positions:
                msg = f"Max active positions reached ({len(open_trades)}/{self.max_open_positions}). Scanner on standby."
                self.last_log = msg
                logger.info(msg)
                return {"success": True, "executed": False, "reason": msg, "scanner_diagnostics": self.scanner_diagnostics}
        except Exception as e:
            active_symbols = set()
            logger.warning(f"Failed to check open trades: {e}")

        # 2. Evaluate target symbol or all watched symbols concurrently
        valid_candidates = []
        symbols_to_scan = [requested_symbol] if requested_symbol else self.watched_symbols

        def _evaluate_single_symbol(sym: str):
            if not requested_symbol and self._stop_event.is_set():
                return {"symbol": sym, "diag": {"symbol": sym, "is_valid": False, "score": 0.0, "status_label": "STOPPED", "reasons": ["Loop stopped"]}, "candidate": None}

            if sym in active_symbols:
                return {
                    "symbol": sym,
                    "diag": {
                        "symbol": sym,
                        "is_valid": False,
                        "score": 0.0,
                        "status_label": "POSITION ACTIVE",
                        "reasons": ["Position currently open in portfolio"]
                    },
                    "candidate": None
                }

            try:
                klines = client.get_klines(sym, interval="1h", limit=50)
                if not klines:
                    return {
                        "symbol": sym,
                        "diag": {"symbol": sym, "is_valid": False, "score": 0.0, "status_label": "NO DATA", "reasons": ["No klines returned"]},
                        "candidate": None
                    }

                order_flow = analyze_order_flow(sym, klines)
                current_price = order_flow.current_price
                if current_price <= 0:
                    p_info = client.get_price(sym)
                    current_price = p_info.get("price", 0.0)

                eval_res = evaluate_master_strategy_setup(
                    symbol=sym,
                    current_price=current_price,
                    order_flow=order_flow,
                    gamma_profile=None
                )

                cand = None
                if eval_res.get("is_valid"):
                    cand = {
                        "symbol": sym,
                        "eval": eval_res,
                        "current_price": current_price,
                        "order_flow": order_flow
                    }

                return {
                    "symbol": sym,
                    "diag": eval_res,
                    "candidate": cand
                }
            except Exception as e:
                logger.warning(f"Failed scan for {sym}: {e}")
                return {
                    "symbol": sym,
                    "diag": {
                        "symbol": sym,
                        "is_valid": False,
                        "score": 0.0,
                        "status_label": "SCAN ERROR",
                        "reasons": [str(e)]
                    },
                    "candidate": None
                }

        # Fast parallel execution across watched symbols
        max_workers = min(5, len(symbols_to_scan))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            scan_results = list(executor.map(_evaluate_single_symbol, symbols_to_scan))

        for item in scan_results:
            self.scanner_diagnostics[item["symbol"]] = item["diag"]
            if item["candidate"]:
                valid_candidates.append(item["candidate"])

        # 3. STRICT MASTER STRATEGY GATE
        if not valid_candidates:
            if requested_symbol:
                diag = self.scanner_diagnostics.get(requested_symbol, {})
                if diag.get("status_label") == "POSITION ACTIVE":
                    msg = f"Position already active for {requested_symbol}. Position Guardian is managing dynamic TP/SL 24/7."
                else:
                    reasons_str = " | ".join(diag.get("reasons", [])) if diag.get("reasons") else "Score < 70%"
                    msg = f"Scan on {requested_symbol} complete: Setup criteria not met ({reasons_str}). Capital preserved."
            else:
                msg = f"Radar scan across {len(self.watched_symbols)} crypto pairs complete: 0 setups with Master Strategy confluence. Capital preserved."
            self.last_log = msg
            logger.info(msg)

            try:
                from backend.api.websocket import sio
                async def _emit_hold():
                    await sio.emit("reasoning_event", {
                        "agent": "AutoTrader",
                        "message": f"Scan for {requested_symbol or 'Crypto Watchlist'}: Strict confluence criteria not met. Holding USDT safely.",
                        "confidence": 0.95
                    })
                threading.Thread(target=lambda: asyncio.run(_emit_hold()), daemon=True).start()
            except Exception:
                pass

            return {
                "success": True,
                "executed": False,
                "symbol": requested_symbol,
                "reason": msg,
                "scanner_diagnostics": self.scanner_diagnostics
            }

        # 4. Pick highest-confluence candidate
        best = max(valid_candidates, key=lambda c: c["eval"]["score"])
        chosen_symbol = best["symbol"]
        current_price = best["current_price"]
        eval_data = best["eval"]
        levels = eval_data["levels"]
        tp_price = levels["take_profit_price"]
        sl_price = levels["stop_loss_price"]

        # 5. Place Paper Order on Binance Spot Testnet
        # Size position safely at 2.0% of NAV (~$200 USDT)
        order_quote_qty = 200.0
        calculated_qty = round(order_quote_qty / current_price, 5) if current_price > 0 else 0.001

        order_res = client.place_order(
            symbol=chosen_symbol,
            side="BUY",
            order_type="MARKET",
            quote_quantity=order_quote_qty
        )
        order_id = str(order_res.get("order_id", f"BINANCE-{int(time.time())}"))
        order_type = "SPOT_MARKET"

        # 6. Build and persist TradeRecord to SQLite ledger
        proposal = TradeProposal(
            id=order_id,
            symbol=chosen_symbol,
            underlying=chosen_symbol,
            strategy_type=StrategyType.MASTER_ORDER_FLOW,
            side="BUY",
            order_type="MARKET",
            qty=calculated_qty,
            quote_qty=order_quote_qty,
            entry_price=current_price,
            take_profit=tp_price,
            stop_loss=sl_price,
            max_profit=round(current_price * (levels["take_profit_pct"] / 100) * calculated_qty, 2),
            max_loss=round(current_price * (levels["stop_loss_pct"] / 100) * calculated_qty, 2),
            breakevens=[round(current_price, 2)],
            thesis=f"Master Strategy Execution ({eval_data['status_label']}, Score {eval_data['score']}): TP ${tp_price} ({levels['tp_reason']}) | SL ${sl_price} ({levels['sl_reason']}) [R:R {levels['risk_reward_ratio']}:1]"
        )

        trade_rec = TradeRecord(
            trade_id=order_id,
            proposal=proposal,
            status=TradeStatus.OPEN,
            entry_time=datetime.now().isoformat(),
            entry_price=current_price,
            realized_pnl=0.0,
            take_profit_price=tp_price,
            stop_loss_price=sl_price,
            binance_order_id=order_id
        )

        def _save():
            asyncio.run(trade_log.save_trade(trade_rec))
        threading.Thread(target=_save, daemon=True).start()

        self.total_automated_trades += 1
        result = {
            "success": True,
            "executed": True,
            "trade_id": order_id,
            "symbol": chosen_symbol,
            "strategy": "MASTER_ORDER_FLOW",
            "score": eval_data["score"],
            "status_label": eval_data["status_label"],
            "reasons": eval_data["reasons"],
            "order_type": order_type,
            "entry_price": current_price,
            "take_profit_price": tp_price,
            "stop_loss_price": sl_price,
            "take_profit_pct": levels["take_profit_pct"],
            "stop_loss_pct": levels["stop_loss_pct"],
            "tp_reason": levels["tp_reason"],
            "sl_reason": levels["sl_reason"],
            "risk_reward_ratio": levels["risk_reward_ratio"],
            "timestamp": datetime.now().isoformat(),
            "scanner_diagnostics": self.scanner_diagnostics
        }

        self.last_trade_result = result
        self.last_log = f"Master Strategy triggered {chosen_symbol} (Score {eval_data['score']})! TP: ${tp_price} | SL: ${sl_price}"
        logger.info(self.last_log)

        # 7. Broadcast real-time WebSocket event
        try:
            from backend.api.websocket import sio
            async def _emit():
                await sio.emit("reasoning_event", {
                    "agent": "AutoTrader",
                    "message": f"High-Confluence Master Strategy Setup ({eval_data['status_label']}, Score {eval_data['score']}) triggered on {chosen_symbol}! Spot Order Dispatched on Binance Testnet. TP: ${tp_price} | SL: ${sl_price}",
                    "confidence": eval_data["score"]
                })
            threading.Thread(target=lambda: asyncio.run(_emit()), daemon=True).start()
        except Exception:
            pass

        return result


# Singleton instance
auto_trader = AutoTrader()
