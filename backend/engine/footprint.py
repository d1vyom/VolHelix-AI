import math
from typing import Dict, Tuple
from backend.engine.flow_models import FootprintBar, FootprintCell
from backend.marketdata.models import Trade
from backend.config import settings

def round_to_tick(price: float, tick_group: float) -> float:
    return round(math.floor(price / tick_group) * tick_group, 8)

class FootprintEngine:
    def __init__(self, symbol: str, interval: str, tick_size: float):
        self.symbol = symbol.upper()
        self.interval = interval
        self.tick_size = tick_size
        self.tick_group = tick_size * settings.FLOW_TICK_GROUP_MULTIPLIER
        self.interval_ms = self._parse_interval(interval)
        self.current_bar: FootprintBar | None = None
        self.cells_dict: Dict[float, FootprintCell] = {}
        
    def _parse_interval(self, interval: str) -> int:
        unit = interval[-1]
        val = int(interval[:-1])
        if unit == 'm': return val * 60 * 1000
        if unit == 'h': return val * 3600 * 1000
        if unit == 'd': return val * 86400 * 1000
        return 60000

    def process_trade(self, trade: Trade) -> Tuple[FootprintBar | None, FootprintBar]:
        """
        Process a trade. Returns (closed_bar, forming_bar).
        If a rollover happens, closed_bar is not None.
        """
        open_time = (trade.ts // self.interval_ms) * self.interval_ms
        closed_bar = None
        
        if self.current_bar is None:
            self._init_bar(open_time, trade.price)
        elif self.current_bar.open_time != open_time:
            closed_bar = self._close_bar()
            self._init_bar(open_time, trade.price)
            
        bar = self.current_bar
        assert bar is not None
        
        bar.high = max(bar.high, trade.price)
        bar.low = min(bar.low, trade.price)
        bar.close = trade.price
        bar.volume += trade.qty
        
        bucket = round_to_tick(trade.price, self.tick_group)
        if bucket not in self.cells_dict:
            self.cells_dict[bucket] = FootprintCell(price=bucket)
            
        cell = self.cells_dict[bucket]
        
        # Aggressor logic:
        # trade.side == "BUY" means BUY aggressor -> positive delta, added to buy_volume
        if trade.side == "BUY":
            cell.buy_volume += trade.qty
            cell.delta += trade.qty
            bar.delta += trade.qty
        else:
            cell.sell_volume += trade.qty
            cell.delta -= trade.qty
            bar.delta -= trade.qty
            
        cell.total_volume += trade.qty
        cell.trades += (trade.last_id - trade.first_id + 1)
        
        bar.max_delta = max(bar.max_delta, bar.delta)
        bar.min_delta = min(bar.min_delta, bar.delta)
        bar.delta_percent = bar.delta / bar.volume if bar.volume > 0 else 0.0
        
        return closed_bar, bar
        
    def _init_bar(self, open_time: int, price: float):
        self.cells_dict.clear()
        self.current_bar = FootprintBar(
            symbol=self.symbol,
            interval=self.interval,
            open_time=open_time,
            close_time=open_time + self.interval_ms - 1,
            open=price,
            high=price,
            low=price,
            close=price,
            tick_group=self.tick_group
        )
        
    def _close_bar(self) -> FootprintBar:
        bar = self.current_bar
        assert bar is not None
        bar.is_closed = True
        
        sorted_prices = sorted(self.cells_dict.keys())
        bar.cells = [self.cells_dict[p] for p in sorted_prices]
        
        # 1. Diagonal imbalance
        for i in range(len(bar.cells)):
            c = bar.cells[i]
            
            if i > 0 and c.buy_volume >= settings.FLOW_IMBALANCE_MIN_VOLUME:
                prev_sell = bar.cells[i-1].sell_volume
                if prev_sell == 0:
                    c.buy_imbalance = True
                elif c.buy_volume >= settings.FLOW_IMBALANCE_RATIO * prev_sell:
                    c.buy_imbalance = True
                    
            if i < len(bar.cells) - 1 and c.sell_volume >= settings.FLOW_IMBALANCE_MIN_VOLUME:
                next_buy = bar.cells[i+1].buy_volume
                if next_buy == 0:
                    c.sell_imbalance = True
                elif c.sell_volume >= settings.FLOW_IMBALANCE_RATIO * next_buy:
                    c.sell_imbalance = True

        # 2. Stacked imbalances
        stacked_min = settings.FLOW_STACKED_IMBALANCE_MIN
        
        current_stack = []
        for c in bar.cells:
            if c.buy_imbalance:
                current_stack.append(c.price)
            else:
                if len(current_stack) >= stacked_min:
                    bar.stacked_buy_imbalance_zones.append([min(current_stack), max(current_stack)])
                current_stack = []
        if len(current_stack) >= stacked_min:
            bar.stacked_buy_imbalance_zones.append([min(current_stack), max(current_stack)])
            
        current_stack = []
        for c in bar.cells:
            if c.sell_imbalance:
                current_stack.append(c.price)
            else:
                if len(current_stack) >= stacked_min:
                    bar.stacked_sell_imbalance_zones.append([min(current_stack), max(current_stack)])
                current_stack = []
        if len(current_stack) >= stacked_min:
            bar.stacked_sell_imbalance_zones.append([min(current_stack), max(current_stack)])

        # 3. POC / Value Area
        if bar.cells:
            vwap = sum(c.price * c.total_volume for c in bar.cells) / bar.volume if bar.volume > 0 else bar.close
            
            # Find POC
            max_vol = max(c.total_volume for c in bar.cells)
            ties = [c for c in bar.cells if c.total_volume == max_vol]
            poc_cell = min(ties, key=lambda c: abs(c.price - vwap))
            bar.poc_price = poc_cell.price
            
            poc_idx = bar.cells.index(poc_cell)
            va_vol = poc_cell.total_volume
            target_vol = settings.FLOW_VALUE_AREA_PCT * bar.volume
            
            up_idx = poc_idx + 1
            down_idx = poc_idx - 1
            
            while va_vol < target_vol and (up_idx < len(bar.cells) or down_idx >= 0):
                vol_up = 0
                if up_idx < len(bar.cells):
                    vol_up += bar.cells[up_idx].total_volume
                if up_idx + 1 < len(bar.cells):
                    vol_up += bar.cells[up_idx+1].total_volume
                    
                vol_down = 0
                if down_idx >= 0:
                    vol_down += bar.cells[down_idx].total_volume
                if down_idx - 1 >= 0:
                    vol_down += bar.cells[down_idx-1].total_volume
                    
                if vol_up == 0 and vol_down == 0:
                    break
                    
                if vol_up > vol_down:
                    va_vol += vol_up
                    up_idx += 2
                elif vol_down > vol_up:
                    va_vol += vol_down
                    down_idx -= 2
                else:
                    va_vol += vol_up + vol_down
                    up_idx += 2
                    down_idx -= 2
                    
            up_clamped = min(up_idx - 1, len(bar.cells) - 1) if up_idx > 0 else 0
            down_clamped = max(down_idx + 1, 0)
            
            # Ensure VAH >= VAL
            if up_clamped < down_clamped:
                up_clamped, down_clamped = down_clamped, up_clamped
                
            bar.vah = bar.cells[up_clamped].price if bar.cells else 0.0
            bar.val = bar.cells[down_clamped].price if bar.cells else 0.0
            bar.value_area_volume = va_vol
            
        # 4. Absorption
        if bar.volume > 0:
            if bar.delta_percent <= -0.25 and (bar.close - bar.low) / (bar.high - bar.low + 1e-8) >= 0.66:
                bar.absorption = "SELL_ABSORBED"
            elif bar.delta_percent >= 0.25 and (bar.high - bar.close) / (bar.high - bar.low + 1e-8) >= 0.66:
                bar.absorption = "BUY_ABSORBED"
                
        return bar
