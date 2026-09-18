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

def evaluate_flow_confluence(
    symbol: str, 
    metrics: FlowMetrics, 
    bars: list, 
    side_bias: str
) -> dict:
    """
    Evaluates order flow confluence to augment the master strategy.
    Returns: {score, components, reasons, veto, veto_reason}
    """
    reasons = []
    components = {}
    veto = False
    veto_reason = None
    score = 0.0

    # 1. Stale stream veto
    if metrics.health.status != "LIVE":
        return {
            "score": 0.0,
            "components": {},
            "reasons": ["Flow data not live"],
            "veto": True,
            "veto_reason": "Flow data not live"
        }

    # 2. CVD Divergence veto
    if side_bias == "BUY" and metrics.cvd_divergence == "BEARISH":
        veto = True
        veto_reason = "Bearish CVD divergence opposes BULLISH bias"
    elif side_bias == "SELL" and metrics.cvd_divergence == "BULLISH":
        veto = True
        veto_reason = "Bullish CVD divergence opposes BEARISH bias"
        
    if veto:
        return {
            "score": 0.0,
            "components": {},
            "reasons": [veto_reason],
            "veto": True,
            "veto_reason": veto_reason
        }

    # 3. Spread ceiling veto
    if metrics.spread_bps > 5.0:
        veto = True
        veto_reason = f"Spread too wide ({metrics.spread_bps:.1f} bps > 5.0)"
        return {
            "score": 0.0,
            "components": {},
            "reasons": [veto_reason],
            "veto": True,
            "veto_reason": veto_reason
        }

    # 4. Data insufficiency veto
    if len(bars) < 20 or metrics.health.gap_events > 0:
        veto = True
        veto_reason = "Insufficient closed bars (<20) or recent data gaps"
        return {
            "score": 0.0,
            "components": {},
            "reasons": [veto_reason],
            "veto": True,
            "veto_reason": veto_reason
        }

    # CVD trend (0.30)
    cvd_score = 0.0
    if side_bias == "BUY" and metrics.cvd_slope > 0 and metrics.session_cvd > 0:
        cvd_score = 0.30
        reasons.append("CVD trending up")
    elif side_bias == "SELL" and metrics.cvd_slope < 0 and metrics.session_cvd < 0:
        cvd_score = 0.30
        reasons.append("CVD trending down")
    components["cvd_trend"] = cvd_score
    score += cvd_score

    # Stacked imbalance (0.25)
    stack_score = 0.0
    if side_bias == "BUY" and metrics.stacked_imbalance_bias == "BUY":
        stack_score = 0.25
        reasons.append("Buy-stacked imbalance zone below (Support)")
    elif side_bias == "SELL" and metrics.stacked_imbalance_bias == "SELL":
        stack_score = 0.25
        reasons.append("Sell-stacked imbalance zone above (Resistance)")
    components["stacked_imbalance"] = stack_score
    score += stack_score

    # Absorption (0.20)
    abs_score = 0.0
    if side_bias == "BUY" and metrics.absorption_flag == "SELL_ABSORBED":
        abs_score = 0.20
        reasons.append("Sellers being absorbed")
    elif side_bias == "SELL" and metrics.absorption_flag == "BUY_ABSORBED":
        abs_score = 0.20
        reasons.append("Buyers being absorbed")
    components["absorption"] = abs_score
    score += abs_score

    # Book imbalance (0.15) - Note: simplified sustained check since we don't track 5s history here easily, assume current state
    book_score = 0.0
    if side_bias == "BUY" and metrics.book_imbalance > 0.15:
        book_score = 0.15
        reasons.append("Bullish book imbalance (>+0.15)")
    elif side_bias == "SELL" and metrics.book_imbalance < -0.15:
        book_score = 0.15
        reasons.append("Bearish book imbalance (<-0.15)")
    components["book_imbalance"] = book_score
    score += book_score

    # Value/POC location (0.10)
    val_score = 0.0
    if side_bias == "BUY" and metrics.price_vs_value in ["IN_VALUE", "ABOVE_VALUE"] and metrics.price >= metrics.val:
        val_score = 0.10
        reasons.append("Price holding above Value Area Low")
    elif side_bias == "SELL" and metrics.price_vs_value in ["IN_VALUE", "BELOW_VALUE"] and metrics.price <= metrics.vah:
        val_score = 0.10
        reasons.append("Price rejecting from Value Area High")
    components["value_location"] = val_score
    score += val_score

    return {
        "score": score,
        "components": components,
        "reasons": reasons,
        "veto": False,
        "veto_reason": None
    }
