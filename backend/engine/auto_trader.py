import time
import math
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
from backend.exchange import registry
from backend.exchange.lifecycle import reconcile_trade, close_trade_position, execute_entry, recover_entries
from backend.exchange.schemas import OrderRequest
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
        self._event_loop = None
        self._event_futures = set()
        self._event_slots = threading.BoundedSemaphore(32)

    def bind_event_loop(self, loop) -> None:
        """Bind notifications to the application loop owned by lifespan."""
        self._event_loop=loop

    def _schedule_event(self, factory) -> None:
        loop=self._event_loop
        if loop is None or not loop.is_running() or not self._event_slots.acquire(blocking=False):
            return
        coroutine=factory()
        try:
            future=asyncio.run_coroutine_threadsafe(coroutine,loop)
        except Exception:
            coroutine.close()
            self._event_slots.release()
            return
        self._event_futures.add(future)
        def finished(done):
            self._event_futures.discard(done)
            self._event_slots.release()
            if not done.cancelled() and done.exception():
                logger.warning('Trading notification unavailable; execution remains in ledger')
        future.add_done_callback(finished)

    async def stop_events(self) -> None:
        """Cancel and await bounded notifications after the trading threads stop."""
        self._event_loop=None
        pending=list(self._event_futures)
        for future in pending:
            future.cancel()
        await asyncio.gather(*(asyncio.wrap_future(future) for future in pending),return_exceptions=True)

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
        asyncio.run(recover_entries())
        # Each order/market is isolated: unavailable Spot data cannot stop Futures.
        for trade in asyncio.run(trade_log.get_pending_trades()):
            try:
                client=registry.get_exchange_client(trade.market)
                asyncio.run(reconcile_trade(trade,client=client))
            except Exception as exc:
                logger.warning(f'Pending reconciliation retained {trade.trade_id}: {exc}')
        for trade in asyncio.run(trade_log.get_open_trades()):
            try:
                client=registry.get_exchange_client(trade.market)
                if trade.exit_client_order_id:
                    asyncio.run(close_trade_position(trade,client=client))
                    continue
                price=float(client.get_price(trade.proposal.symbol)['price'])
                if not math.isfinite(price) or price<=0:
                    continue
                long=trade.proposal.side=='BUY'
                tp=trade.take_profit_price or trade.proposal.take_profit
                sl=trade.stop_loss_price or trade.proposal.stop_loss
                hit_tp=tp and (price>=tp if long else price<=tp)
                hit_sl=sl and (price<=sl if long else price>=sl)
                if hit_tp or hit_sl:
                    self._close_position_and_finalize_trade(client=client,trade=trade,
                        symbol=trade.proposal.symbol,exit_price=price,entry_price=trade.entry_price,
                        qty=trade.proposal.qty,exit_type='TAKE_PROFIT' if hit_tp else 'STOP_LOSS',
                        reason='Confirmed market price crossed protective threshold')
            except Exception as exc:
                logger.warning(f'Guardian retained {trade.trade_id}: {exc}')

    def _close_position_and_finalize_trade(self,client,trade,symbol,exit_price,entry_price,qty,exit_type,reason):
        status=TradeStatus.TAKE_PROFIT if exit_type=='TAKE_PROFIT' else TradeStatus.STOPPED_OUT
        updated=asyncio.run(close_trade_position(trade,client=client,exit_type=status))
        if updated.exit_price is not None:
            self._emit_guardian_event(exit_type,symbol,updated.exit_price,updated.realized_pnl,
                f'{trade.market} {symbol}: {updated.status.value}; remaining {updated.proposal.qty}. {reason}',
                market=updated.market,trade_id=updated.trade_id,status=updated.status.value,qty=updated.proposal.qty)

    def _emit_guardian_event(self, exit_type: str, symbol: str, price: float, pnl: float, message: str,
                             *, market='spot', trade_id=None, status='CLOSED', qty=0):
        try:
            from backend.api.websocket import sio
            async def _emit():
                await sio.emit("reasoning_event", {
                    "agent": "RiskGate",
                    "message": message,
                    "confidence": 1.0
                })
                await sio.emit("trade_executed", {
                    "trade_id": trade_id,
                    "market": market,
                    "symbol": symbol,
                    "status": status,
                    "qty": qty,
                    "realized_pnl": pnl,
                    "exit_price": price
                })
            self._schedule_event(_emit)
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
            self._schedule_event(_emit)
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

    def shutdown(self) -> None:
        """Signal and join owned trading loops before application resources close."""
        self._stop_event.set()
        self._guardian_stop_event.set()
        self.is_running=False
        for worker in (self._worker_thread,self._guardian_thread):
            if worker and worker.is_alive() and threading.current_thread()!=worker:
                worker.join()

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

                # Phase 9: Flow Confluence
                from backend.marketdata.hub import MarketDataHub
                from backend.engine.flow_confluence import evaluate_flow_confluence
                hub = MarketDataHub()
                flow_eval = None
                metrics = hub.get_metrics(sym)
                
                # Fetch bars for the primary interval if available
                # Assuming 1m is the base interval in FLOW_FOOTPRINT_INTERVALS
                bars = hub.get_footprint_bars(sym, "1m")
                
                if metrics:
                    side_bias = "BUY" if order_flow.trend_bias in ["BULLISH", "NEUTRAL"] else "SELL"
                    flow_eval = evaluate_flow_confluence(sym, metrics, bars, side_bias)
                    if not settings.FLOW_CONFLUENCE_ENABLED:
                        # Shadow Mode logging
                        shadow_eval = evaluate_master_strategy_setup(
                            symbol=sym, current_price=current_price, order_flow=order_flow, gamma_profile=None, flow=flow_eval
                        )
                        orig_eval = evaluate_master_strategy_setup(
                            symbol=sym, current_price=current_price, order_flow=order_flow, gamma_profile=None, flow=None
                        )
                        logger.info(f"SHADOW: {sym} old_score={orig_eval['score']} new_score={shadow_eval['score']} old_valid={orig_eval['is_valid']} new_valid={shadow_eval['is_valid']}")

                eval_res = evaluate_master_strategy_setup(
                    symbol=sym,
                    current_price=current_price,
                    order_flow=order_flow,
                    gamma_profile=None,
                    flow=flow_eval
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
                self._schedule_event(_emit_hold)
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

        # The shared dispatch path rechecks fresh risk and persists intent first.
        try:
            request=OrderRequest(symbol=chosen_symbol,side=eval_data.get('side','BUY'),quote_quantity=200)
            order_result,trade_rec=asyncio.run(execute_entry(request,client=client))
        except Exception as exc:
            return {'success':False,'executed':False,'symbol':chosen_symbol,'reason':str(exc),
                    'scanner_diagnostics':self.scanner_diagnostics}
        order_id=trade_rec.trade_id
        order_type='SPOT_MARKET'
        current_price=trade_rec.entry_price
        tp_price=trade_rec.take_profit_price
        sl_price=trade_rec.stop_loss_price

        self.total_automated_trades += 1
        result = {
            "success": True,
            "executed": order_result.executed_qty>0,
            "exchange_status":order_result.exchange_status,
            "status":trade_rec.status.value,
            "qty":order_result.executed_qty,
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
            self._schedule_event(_emit)
        except Exception:
            pass

        return result


# Singleton instance
auto_trader = AutoTrader()
