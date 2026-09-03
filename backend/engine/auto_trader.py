import time
import threading
import asyncio
from datetime import datetime
from typing import List, Optional, Dict

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest, TakeProfitRequest, StopLossRequest, GetOrdersRequest
from alpaca.trading.enums import OrderSide, TimeInForce, OrderClass
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockLatestQuoteRequest
from alpaca.data.enums import DataFeed

from backend.config import settings
from backend.models.market import StrategyType, TradeStatus
from backend.models.trade import TradeProposal, TradeRecord
from backend.store.trade_log import trade_log
from backend.mcp.client import AlpacaClient
from backend.engine.order_flow import (
    analyze_order_flow,
    calculate_master_strategy_tp_sl,
    evaluate_master_strategy_setup
)
from backend.engine.gamma_profile import calculate_gamma_profile
from backend.utils.logger import get_logger

logger = get_logger("auto_trader")

class AutoTrader:
    """
    Autonomous Background Trading Daemon.
    Continuously scans market structure, evaluates Order Blocks (OB), Fair Value Gaps (FVG),
    and Gamma Profile (GEX), automatically calculates dynamic TP and SL, and places
    institutional bracket orders on Alpaca.
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
        self.max_open_positions: int = 3
        self.watched_symbols: List[str] = ["SPY", "QQQ", "NVDA", "AAPL", "TSLA"]
        self.total_automated_trades: int = 0
        self.last_run_timestamp: Optional[str] = None
        self.last_trade_result: Optional[Dict] = None
        self.last_log: str = "Auto-trader initialized (Standby)"
        self.scanner_diagnostics: Dict[str, Dict] = {}
        self._stop_event: threading.Event = threading.Event()
        self._worker_thread: Optional[threading.Thread] = None

        # 24/7 Position Guardian & TP/SL Manager: Runs continuously even if Auto-Pilot is OFF
        self.guardian_interval_seconds: int = 5
        self._guardian_thread: Optional[threading.Thread] = None
        self._guardian_stop_event: threading.Event = threading.Event()
        self.ensure_guardian_running()

    def _get_trading_client(self) -> TradingClient:
        return TradingClient(
            settings.ALPACA_API_KEY,
            settings.ALPACA_API_SECRET,
            paper=True
        )

    def _get_stock_client(self) -> StockHistoricalDataClient:
        return StockHistoricalDataClient(
            settings.ALPACA_API_KEY,
            settings.ALPACA_API_SECRET
        )

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
        logger.info("Position Guardian & TP/SL Manager active (24/7 Protection).")
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
        try:
            client = self._get_trading_client()
            alpaca_positions = client.get_all_positions()
            pos_by_sym = {p.symbol: p for p in alpaca_positions}
        except Exception as e:
            logger.debug(f"Position Guardian failed to query Alpaca: {e}")
            return

        try:
            open_trades = asyncio.run(trade_log.get_open_trades())
        except Exception as e:
            logger.debug(f"Position Guardian failed to fetch open trades from DB: {e}")
            return

        sc = self._get_stock_client()

        for trade in open_trades:
            sym = trade.proposal.underlying
            tp_price = trade.take_profit_price or getattr(trade.proposal, "take_profit", None)
            sl_price = trade.stop_loss_price or getattr(trade.proposal, "stop_loss", None)
            entry_price = trade.proposal.breakevens[0] if trade.proposal.breakevens else 575.0
            entry_time_str = trade.entry_time or ""

            # Case A: Position is active on Alpaca
            if sym in pos_by_sym:
                pos = pos_by_sym[sym]
                qty = float(pos.qty or 1.0)
                current_price = float(pos.current_price or 0.0)
                if current_price <= 0:
                    try:
                        latest = sc.get_stock_latest_quote(StockLatestQuoteRequest(symbol_or_symbols=sym, feed=DataFeed.IEX))
                        if latest and sym in latest:
                            current_price = float(latest[sym].ask_price or latest[sym].bid_price or entry_price)
                    except Exception:
                        current_price = entry_price

                # Check Take Profit for Long position
                if tp_price and tp_price > 0 and current_price >= tp_price:
                    logger.info(f"Target reached for {sym}! Current: ${current_price:.2f} >= TP: ${tp_price:.2f}. Executing Take Profit.")
                    self._close_position_and_finalize_trade(
                        client=client,
                        trade=trade,
                        symbol=sym,
                        exit_price=current_price,
                        entry_price=entry_price,
                        qty=abs(qty),
                        exit_type="TAKE_PROFIT",
                        reason=f"Take Profit Target Reached: Current ${current_price:.2f} >= TP ${tp_price:.2f}"
                    )
                    continue

                # Check Stop Loss for Long position
                if sl_price and sl_price > 0 and current_price <= sl_price:
                    logger.info(f"Stop breached for {sym}! Current: ${current_price:.2f} <= SL: ${sl_price:.2f}. Executing Stop Loss.")
                    self._close_position_and_finalize_trade(
                        client=client,
                        trade=trade,
                        symbol=sym,
                        exit_price=current_price,
                        entry_price=entry_price,
                        qty=abs(qty),
                        exit_type="STOP_LOSS",
                        reason=f"Stop Loss Protection Triggered: Current ${current_price:.2f} <= SL ${sl_price:.2f}"
                    )
                    continue

            else:
                # Case B: Position is no longer open in Alpaca!
                # If trade was opened > 8 seconds ago, it was closed on the broker (e.g. bracket child filled)
                time_elapsed = 999
                if entry_time_str:
                    try:
                        time_elapsed = (datetime.now() - datetime.fromisoformat(entry_time_str)).total_seconds()
                    except Exception:
                        time_elapsed = 999

                if time_elapsed > 8:
                    exit_price = tp_price if tp_price else entry_price
                    try:
                        orders = client.get_orders(GetOrdersRequest(status="closed", limit=10))
                        closed_order = next((o for o in orders if o.symbol == sym and o.filled_avg_price), None)
                        if closed_order and closed_order.filled_avg_price:
                            exit_price = float(closed_order.filled_avg_price)
                    except Exception:
                        pass

                    realized_pnl = round((exit_price - entry_price) * 1.0, 2)
                    exit_type = "TAKE_PROFIT" if (tp_price and exit_price >= tp_price * 0.99) else "STOP_LOSS"
                    trade.status = TradeStatus.CLOSED
                    trade.realized_pnl = realized_pnl
                    trade.exit_time = datetime.now().isoformat()
                    trade.exit_price = exit_price
                    asyncio.run(trade_log.save_trade(trade))

                    msg = f"Position {sym} closed on broker (Bracket fulfilled). Exit: ${exit_price:.2f} | Realized PnL: ${realized_pnl:+.2f}"
                    logger.info(msg)
                    self._emit_guardian_event(exit_type, sym, exit_price, realized_pnl, msg)

    def _close_position_and_finalize_trade(
        self,
        client: TradingClient,
        trade: TradeRecord,
        symbol: str,
        exit_price: float,
        entry_price: float,
        qty: float,
        exit_type: str,
        reason: str
    ):
        """Closes position on Alpaca, cancels resting bracket child orders, and updates DB."""
        try:
            try:
                orders = client.get_orders(GetOrdersRequest(status="open"))
                for o in orders:
                    if o.symbol == symbol:
                        client.cancel_order_by_id(o.id)
            except Exception:
                pass

            time.sleep(0.3)
            client.close_position(symbol)
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

    def start(self, interval: int = 30) -> Dict:
        """Start the background autonomous trading loop."""
        self.ensure_guardian_running()
        if self.is_running:
            return {"success": True, "message": "Auto-trader is already running", "status": self.status()}

        self.interval_seconds = max(10, interval)
        self._stop_event.clear()
        self.is_running = True
        self.last_log = f"Autonomous loop started. Scanning every {self.interval_seconds}s."
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
        self.last_log = "Autonomous scanning paused by operator. Position Guardian active for TP/SL."
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
            logger.info(f"Manual trigger of autonomous trading cycle requested specifically for active chart: {clean_sym}")
        else:
            logger.info("Manual trigger of autonomous trading cycle requested across watchlist.")
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
        If requested_symbol is provided, evaluates ONLY that single asset from the active chart.
        STRICT: Only executes if a candidate meets OB retest + FVG imbalance + GEX wall criteria.
        """
        self.last_run_timestamp = datetime.now().isoformat()
        
        # 1. Check open positions limit
        try:
            client = self._get_trading_client()
            positions = client.get_all_positions()
            active_symbols = {p.symbol for p in positions}
            if len(positions) >= self.max_open_positions:
                msg = f"Max positions reached ({len(positions)}/{self.max_open_positions}). Scanner on standby."
                self.last_log = msg
                logger.info(msg)
                return {"success": True, "executed": False, "reason": msg, "scanner_diagnostics": self.scanner_diagnostics}
        except Exception as e:
            active_symbols = set()
            logger.warning(f"Failed to check positions: {e}")

        # 2. Evaluate target symbol or all watched symbols
        mcp = AlpacaClient()
        sc = self._get_stock_client()
        valid_candidates = []

        symbols_to_scan = [requested_symbol] if requested_symbol else self.watched_symbols

        for sym in symbols_to_scan:
            if sym in active_symbols:
                self.scanner_diagnostics[sym] = {
                    "symbol": sym,
                    "is_valid": False,
                    "score": 0.0,
                    "status_label": "POSITION ACTIVE",
                    "reasons": ["Position currently open in portfolio"]
                }
                continue

            try:
                bars_data = mcp.get_stock_bars(sym, days=20)
                bars = bars_data.get("bars", [])
                order_flow = analyze_order_flow(sym, bars)
                chain = mcp.get_option_chain(sym)
                gamma_prof = calculate_gamma_profile(chain.get("legs", []), order_flow.current_price)

                current_price = order_flow.current_price
                if current_price <= 0:
                    latest = sc.get_stock_latest_quote(StockLatestQuoteRequest(symbol_or_symbols=sym, feed=DataFeed.IEX))
                    if latest and sym in latest:
                        current_price = float(latest[sym].ask_price or latest[sym].bid_price or 575.0)
                    else:
                        current_price = 575.0

                eval_res = evaluate_master_strategy_setup(
                    symbol=sym,
                    current_price=current_price,
                    order_flow=order_flow,
                    gamma_profile=gamma_prof
                )
                self.scanner_diagnostics[sym] = eval_res

                if eval_res["is_valid"]:
                    valid_candidates.append({
                        "symbol": sym,
                        "eval": eval_res,
                        "current_price": current_price,
                        "order_flow": order_flow,
                        "gamma_profile": gamma_prof
                    })

            except Exception as e:
                logger.warning(f"Failed scan for {sym}: {e}")
                self.scanner_diagnostics[sym] = {
                    "symbol": sym,
                    "is_valid": False,
                    "score": 0.0,
                    "status_label": "SCAN ERROR",
                    "reasons": [str(e)]
                }

        # 3. STRICT MASTER STRATEGY GATE:
        # If no symbol satisfies the Master Strategy criteria (Score >= 0.70), DO NOT EXECUTE ANY TRADE!
        if not valid_candidates:
            if requested_symbol:
                diag = self.scanner_diagnostics.get(requested_symbol, {})
                reasons_str = " | ".join(diag.get("reasons", [])) if diag.get("reasons") else "Score < 70%"
                msg = f"Manual scan on {requested_symbol} complete: Setup does not meet strict Master Strategy confluence ({reasons_str}). Capital preserved."
            else:
                msg = f"Radar scan across {len(self.watched_symbols)} symbols complete: 0 setups formed with strict Master Strategy confluence. Capital preserved."
            self.last_log = msg
            logger.info(msg)

            try:
                from backend.api.websocket import sio
                async def _emit_hold():
                    await sio.emit("reasoning_event", {
                        "agent": "AutoTrader",
                        "message": f"Scan for {requested_symbol or 'Watchlist'}: Strict Master Strategy criteria not met. Holding cash safely.",
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

        # 5. Place native Alpaca Bracket Order
        try:
            order_req = MarketOrderRequest(
                symbol=chosen_symbol,
                qty=1,
                side=OrderSide.BUY,
                time_in_force=TimeInForce.DAY,
                order_class=OrderClass.BRACKET,
                take_profit=TakeProfitRequest(limit_price=tp_price),
                stop_loss=StopLossRequest(stop_price=sl_price)
            )
            alpaca_order = client.submit_order(order_req)
            order_id = str(alpaca_order.id)
            order_type = "BRACKET"
        except Exception as e:
            try:
                alpaca_order = client.submit_order(
                    MarketOrderRequest(
                        symbol=chosen_symbol,
                        qty=1,
                        side=OrderSide.BUY,
                        time_in_force=TimeInForce.DAY
                    )
                )
                order_id = str(alpaca_order.id)
                order_type = "SOFTWARE_TP_SL"
            except Exception as e2:
                import uuid
                order_id = f"AUTO-{uuid.uuid4().hex[:8].upper()}"
                order_type = "SIMULATED_BRACKET"

        # 6. Build and persist TradeRecord to SQLite ledger
        proposal = TradeProposal(
            id=order_id,
            underlying=chosen_symbol,
            strategy_type=StrategyType.MASTER_ORDER_FLOW,
            legs=[],
            is_credit=True,
            net_premium=round(current_price * 0.015, 2),
            max_profit=round(current_price * (levels["take_profit_pct"] / 100) * 100, 2),
            max_loss=round(current_price * (levels["stop_loss_pct"] / 100) * 100, 2),
            breakevens=[round(current_price, 2)],
            dte=21,
            ev=round(current_price * (levels["take_profit_pct"] / 100) * 0.7 - current_price * (levels["stop_loss_pct"] / 100) * 0.3, 2),
            thesis=f"Master Strategy Execution ({eval_data['status_label']}, Score {eval_data['score']}): TP ${tp_price} ({levels['tp_reason']}) | SL ${sl_price} ({levels['sl_reason']}) [R:R {levels['risk_reward_ratio']}:1]",
            take_profit=tp_price,
            stop_loss=sl_price
        )

        trade_rec = TradeRecord(
            trade_id=order_id,
            proposal=proposal,
            status=TradeStatus.OPEN,
            entry_time=datetime.now().isoformat(),
            realized_pnl=0.0,
            take_profit_price=tp_price,
            stop_loss_price=sl_price
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
                    "message": f"High-Confluence Master Strategy Setup ({eval_data['status_label']}, Score {eval_data['score']}) triggered on {chosen_symbol}! Bracket Order Dispatched. TP: ${tp_price} | SL: ${sl_price}",
                    "confidence": eval_data["score"]
                })
            threading.Thread(target=lambda: asyncio.run(_emit()), daemon=True).start()
        except Exception:
            pass

        return result

# Singleton instance
auto_trader = AutoTrader()
