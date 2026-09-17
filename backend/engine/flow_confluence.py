import time
from typing import Optional, Dict, Any
from backend.marketdata.models import StreamHealth
from backend.engine.flow_models import FlowMetrics
from backend.engine.footprint import FootprintEngine
from backend.engine.delta_engine import DeltaEngine

def build_flow_metrics(
    symbol: str,
    price: float,
    footprint_engine: FootprintEngine,
    delta_engine: DeltaEngine,
    dom_analytics: Optional[Dict[str, Any]],
    health: StreamHealth
) -> FlowMetrics:
    now = int(time.time() * 1000)
    
    delta_metrics = delta_engine.get_metrics()
    vwap, vwap_upper_1, vwap_lower_1 = delta_engine.get_vwap()
    
    bar_delta = 0.0
    delta_percent = 0.0
    poc_price = price
    vah = price
    val = price
    absorption = None
    stacked_bias = "NEUTRAL"
    
    if footprint_engine.current_bar:
        bar = footprint_engine.current_bar
        bar_delta = bar.delta
        delta_percent = bar.delta_percent
        poc_price = bar.poc_price
        vah = bar.vah
        val = bar.val
        absorption = bar.absorption
        
        buy_zones = len(bar.stacked_buy_imbalance_zones)
        sell_zones = len(bar.stacked_sell_imbalance_zones)
        if buy_zones > sell_zones:
            stacked_bias = "BUY"
        elif sell_zones > buy_zones:
            stacked_bias = "SELL"
            
    price_vs_value = "IN_VALUE"
    if price > vah:
        price_vs_value = "ABOVE_VALUE"
    elif price < val:
        price_vs_value = "BELOW_VALUE"
        
    book_imbalance = 0.0
    spread_bps = 0.0
    nearest_bid = None
    nearest_ask = None
    
    if dom_analytics:
        book_imbalance = dom_analytics.get('book_imbalance', 0.0)
        spread_bps = dom_analytics.get('spread_bps', 0.0)
        nearest_bid = dom_analytics.get('nearest_bid_wall')
        nearest_ask = dom_analytics.get('nearest_ask_wall')
        
    trades_count = len(delta_engine.trades_1m)
    vol_sum = sum(t.qty for t in delta_engine.trades_1m)
    trade_rate = trades_count / 60.0
    vol_rate = vol_sum / 60.0
    
    return FlowMetrics(
        symbol=symbol,
        ts=now,
        price=price,
        session_cvd=delta_metrics['session_cvd'],
        bar_delta=bar_delta,
        delta_percent=delta_percent,
        cvd_slope=delta_metrics['cvd_slope'],
        cvd_divergence=delta_metrics['cvd_divergence'],
        buy_sell_ratio=delta_metrics['buy_sell_ratio'],
        aggression_index=delta_metrics['aggression_index'],
        absorption_flag=absorption,
        stacked_imbalance_bias=stacked_bias,
        poc_price=poc_price,
        vah=vah,
        val=val,
        price_vs_value=price_vs_value,
        book_imbalance=book_imbalance,
        spread_bps=spread_bps,
        nearest_bid_wall=nearest_bid,
        nearest_ask_wall=nearest_ask,
        vwap=vwap,
        vwap_upper_1=vwap_upper_1,
        vwap_lower_1=vwap_lower_1,
        trade_rate=trade_rate,
        volume_rate=vol_rate,
        health=health
    )
