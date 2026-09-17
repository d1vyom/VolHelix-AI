import time
import math
from typing import List, Tuple
from backend.marketdata.models import Trade
from backend.engine.flow_models import CVDPoint
from backend.config import settings

class DeltaEngine:
    def __init__(self, symbol: str):
        self.symbol = symbol.upper()
        self.session_cvd: float = 0.0
        self.session_vwap: float = 0.0
        self.session_vol: float = 0.0
        self.session_price_vol: float = 0.0
        self.session_price_sq_vol: float = 0.0
        
        now_ts = int(time.time() * 1000)
        self.session_start_ts: int = self._get_session_start_ts(now_ts)
        
        # 1-minute rolling trades for fast metrics
        self.trades_1m: List[Trade] = []
        
        # CVD points at 1-minute intervals for divergence and slope
        self.cvd_history: List[CVDPoint] = []
        self.last_cvd_point_ts: int = now_ts // 60000 * 60000

    def _get_session_start_ts(self, ts: int) -> int:
        seconds = ts // 1000
        days = seconds // 86400
        return days * 86400 * 1000

    def process_trade(self, trade: Trade):
        # Rollover check
        if trade.ts >= self.session_start_ts + 86400 * 1000:
            self.session_start_ts = self._get_session_start_ts(trade.ts)
            self.session_cvd = 0.0
            self.session_vol = 0.0
            self.session_price_vol = 0.0
            self.session_price_sq_vol = 0.0

        # Update CVD
        delta = trade.qty if trade.side == "BUY" else -trade.qty
        self.session_cvd += delta
        
        # Update VWAP
        self.session_vol += trade.qty
        self.session_price_vol += trade.price * trade.qty
        self.session_price_sq_vol += (trade.price ** 2) * trade.qty
        
        # Rolling 1m window
        self.trades_1m.append(trade)
        cutoff = trade.ts - 60 * 1000
        # fast trim
        while self.trades_1m and self.trades_1m[0].ts < cutoff:
            self.trades_1m.pop(0)
            
        # Record CVD points every 1 min
        if trade.ts - self.last_cvd_point_ts >= 60 * 1000:
            self._add_cvd_point(trade.ts, trade.price)
            self.last_cvd_point_ts = trade.ts

    def _add_cvd_point(self, ts: int, price: float):
        prev_cvd = self.cvd_history[-1].cvd if self.cvd_history else 0.0
        point = CVDPoint(ts=ts, cvd=self.session_cvd, delta=self.session_cvd - prev_cvd, price=price, divergence=None)
        
        lookback = 20
        if len(self.cvd_history) >= lookback:
            window = self.cvd_history[-lookback:] + [point]
            max_p = max(p.price for p in window[:-1])
            min_p = min(p.price for p in window[:-1])
            max_c = max(p.cvd for p in window[:-1])
            min_c = min(p.cvd for p in window[:-1])
            
            noise_floor = 0.001  # 0.1%
            
            if point.price > max_p * (1 + noise_floor) and point.cvd < max_c:
                point.divergence = "BEARISH"
            elif point.price < min_p * (1 - noise_floor) and point.cvd > min_c:
                point.divergence = "BULLISH"
                
        self.cvd_history.append(point)
        if len(self.cvd_history) > 240:
            self.cvd_history.pop(0)

    def get_vwap(self) -> Tuple[float, float, float]:
        """Returns VWAP, upper_1, lower_1"""
        if self.session_vol == 0:
            return 0.0, 0.0, 0.0
        vwap = self.session_price_vol / self.session_vol
        variance = (self.session_price_sq_vol / self.session_vol) - (vwap ** 2)
        std_dev = math.sqrt(max(0, variance))
        return vwap, vwap + std_dev, vwap - std_dev

    def get_metrics(self) -> dict:
        buy_vol = sum(t.qty for t in self.trades_1m if t.side == "BUY")
        sell_vol = sum(t.qty for t in self.trades_1m if t.side == "SELL")
        total_vol = buy_vol + sell_vol
        
        whale_vol = sum(t.qty for t in self.trades_1m if (t.price * t.qty) >= settings.FLOW_WHALE_NOTIONAL_USD)
        
        buy_sell_ratio = buy_vol / max(sell_vol, 1e-8)
        aggression_index = whale_vol / max(total_vol, 1e-8)
        
        cvd_slope = 0.0
        pts = self.cvd_history[-30:]
        if len(pts) > 1:
            n = len(pts)
            xs = [(p.ts - pts[0].ts) / 60000.0 for p in pts]
            ys = [p.cvd for p in pts]
            mean_x = sum(xs) / n
            mean_y = sum(ys) / n
            den = sum((x - mean_x) ** 2 for x in xs)
            if den != 0:
                cvd_slope = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)) / den
                
        divergence = self.cvd_history[-1].divergence if self.cvd_history else None
        
        return {
            "session_cvd": self.session_cvd,
            "buy_sell_ratio": buy_sell_ratio,
            "aggression_index": min(max(aggression_index, 0.0), 1.0),
            "cvd_slope": cvd_slope,
            "cvd_divergence": divergence
        }
