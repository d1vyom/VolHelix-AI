from typing import List, Dict, Literal
from backend.marketdata.models import Trade
from backend.engine.flow_models import VolumeProfileSnapshot, VolumeProfileLevel
from backend.config import settings
from backend.engine.footprint import round_to_tick

def compute_profile_from_trades(symbol: str, trades: List[Trade], mode: Literal["SESSION", "VISIBLE", "FIXED_RANGE"], start_ts: int, end_ts: int, tick_group: float) -> VolumeProfileSnapshot:
    levels_dict: Dict[float, VolumeProfileLevel] = {}
    total_vol = 0.0
    
    for t in trades:
        if not (start_ts <= t.ts <= end_ts):
            continue
        bucket = round_to_tick(t.price, tick_group)
        if bucket not in levels_dict:
            levels_dict[bucket] = VolumeProfileLevel(price=bucket)
            
        level = levels_dict[bucket]
        if t.side == "BUY":
            level.buy_volume += t.qty
            level.delta += t.qty
        else:
            level.sell_volume += t.qty
            level.delta -= t.qty
        level.total_volume += t.qty
        total_vol += t.qty
        
    levels = list(levels_dict.values())
    levels.sort(key=lambda x: x.price)
    
    poc_price = 0.0
    vah = 0.0
    val = 0.0
    
    if levels:
        poc_level = max(levels, key=lambda l: l.total_volume)
        poc_price = poc_level.price
        
        poc_idx = levels.index(poc_level)
        va_vol = poc_level.total_volume
        target_vol = settings.FLOW_VALUE_AREA_PCT * total_vol
        
        up_idx = poc_idx + 1
        down_idx = poc_idx - 1
        
        while va_vol < target_vol and (up_idx < len(levels) or down_idx >= 0):
            vol_up = 0
            if up_idx < len(levels): vol_up += levels[up_idx].total_volume
            if up_idx + 1 < len(levels): vol_up += levels[up_idx+1].total_volume
            
            vol_down = 0
            if down_idx >= 0: vol_down += levels[down_idx].total_volume
            if down_idx - 1 >= 0: vol_down += levels[down_idx-1].total_volume
            
            if vol_up == 0 and vol_down == 0: break
            
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
                
        up_clamped = min(up_idx - 1, len(levels) - 1) if up_idx > 0 else 0
        down_clamped = max(down_idx + 1, 0)
        if up_clamped < down_clamped:
            up_clamped, down_clamped = down_clamped, up_clamped
            
        vah = levels[up_clamped].price
        val = levels[down_clamped].price
        
        for i in range(len(levels)):
            levels[i].is_poc = (i == poc_idx)
            levels[i].in_value_area = (down_clamped <= i <= up_clamped)

    return VolumeProfileSnapshot(
        symbol=symbol,
        mode=mode,
        start_ts=start_ts,
        end_ts=end_ts,
        tick_group=tick_group,
        levels=levels,
        poc_price=poc_price,
        vah=vah,
        val=val,
        total_volume=total_vol,
        naked_pocs=[]  # Filled in by engine
    )

class VolumeProfileEngine:
    def __init__(self, symbol: str, tick_size: float):
        self.symbol = symbol.upper()
        self.tick_group = tick_size * settings.FLOW_TICK_GROUP_MULTIPLIER
        self.session_start_ts = 0
        self.levels_dict: Dict[float, VolumeProfileLevel] = {}
        self.naked_pocs: List[float] = []

    def _get_session_start_ts(self, ts: int) -> int:
        seconds = ts // 1000
        days = seconds // 86400
        return days * 86400 * 1000

    def process_trade(self, trade: Trade):
        session_start = self._get_session_start_ts(trade.ts)
        if self.session_start_ts != session_start:
            self.session_start_ts = session_start
            self.levels_dict.clear()
            self.naked_pocs.clear()
            
        bucket = round_to_tick(trade.price, self.tick_group)
        if bucket not in self.levels_dict:
            self.levels_dict[bucket] = VolumeProfileLevel(price=bucket)
            
        level = self.levels_dict[bucket]
        if trade.side == "BUY":
            level.buy_volume += trade.qty
            level.delta += trade.qty
        else:
            level.sell_volume += trade.qty
            level.delta -= trade.qty
            
        level.total_volume += trade.qty
        
        # Remove tested naked POCs
        if self.naked_pocs:
            self.naked_pocs = [p for p in self.naked_pocs if abs(p - trade.price) > self.tick_group / 2]
            
    def add_naked_poc(self, price: float):
        if price not in self.naked_pocs:
            self.naked_pocs.append(price)

    def get_session_profile(self, ts: int) -> VolumeProfileSnapshot:
        levels = list(self.levels_dict.values())
        levels.sort(key=lambda x: x.price)
        
        total_vol = sum(l.total_volume for l in levels)
        poc_price = 0.0
        vah = 0.0
        val = 0.0
        
        if levels:
            poc_level = max(levels, key=lambda l: l.total_volume)
            poc_price = poc_level.price
            
            poc_idx = levels.index(poc_level)
            va_vol = poc_level.total_volume
            target_vol = settings.FLOW_VALUE_AREA_PCT * total_vol
            
            up_idx = poc_idx + 1
            down_idx = poc_idx - 1
            
            while va_vol < target_vol and (up_idx < len(levels) or down_idx >= 0):
                vol_up = 0
                if up_idx < len(levels): vol_up += levels[up_idx].total_volume
                if up_idx + 1 < len(levels): vol_up += levels[up_idx+1].total_volume
                
                vol_down = 0
                if down_idx >= 0: vol_down += levels[down_idx].total_volume
                if down_idx - 1 >= 0: vol_down += levels[down_idx-1].total_volume
                
                if vol_up == 0 and vol_down == 0: break
                
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
                    
            up_clamped = min(up_idx - 1, len(levels) - 1) if up_idx > 0 else 0
            down_clamped = max(down_idx + 1, 0)
            if up_clamped < down_clamped:
                up_clamped, down_clamped = down_clamped, up_clamped
                
            vah = levels[up_clamped].price
            val = levels[down_clamped].price
            
            for i in range(len(levels)):
                levels[i].is_poc = (i == poc_idx)
                levels[i].in_value_area = (down_clamped <= i <= up_clamped)

        return VolumeProfileSnapshot(
            symbol=self.symbol,
            mode="SESSION",
            start_ts=self.session_start_ts,
            end_ts=ts,
            tick_group=self.tick_group,
            levels=levels,
            poc_price=poc_price,
            vah=vah,
            val=val,
            total_volume=total_vol,
            naked_pocs=list(self.naked_pocs)
        )
