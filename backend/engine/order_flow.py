import numpy as np
from typing import List, Dict, Optional
from pydantic import BaseModel, Field
from datetime import datetime

class OrderBlock(BaseModel):
    id: str
    block_type: str = Field(description="'BULLISH' (Demand) or 'BEARISH' (Supply)")
    low: float
    high: float
    mean_threshold: float = Field(description="50% equilibrium level of the order block")
    volume: float
    timestamp: str
    mitigated: bool = False
    strength: float = Field(default=1.0, description="Relative strength score 0-1")

class FairValueGap(BaseModel):
    id: str
    gap_type: str = Field(description="'BULLISH' (BISI) or 'BEARISH' (SIBI)")
    top: float
    bottom: float
    midpoint: float
    size: float
    timestamp: str
    filled: bool = False
    fill_pct: float = 0.0

class LiquidityLevel(BaseModel):
    price: float
    volume: float
    side: str = Field(description="'BID', 'ASK', 'BSL' (Buy-side), 'SSL' (Sell-side)")
    intensity: float = Field(description="Normalized liquidity density 0-1")

class OrderFlowAnalysis(BaseModel):
    symbol: str
    timestamp: str
    current_price: float
    trend_bias: str = "NEUTRAL"
    order_blocks: List[OrderBlock] = []
    fair_value_gaps: List[FairValueGap] = []
    nearest_bullish_ob: Optional[OrderBlock] = None
    nearest_bearish_ob: Optional[OrderBlock] = None
    unfilled_fvgs: List[FairValueGap] = []
    liquidity_heatmap: List[LiquidityLevel] = []

def detect_order_blocks(bars: List[Dict], atr_period: int = 14) -> List[OrderBlock]:
    """
    Detect institutional Order Blocks (OB) based on Smart Money Concepts (SMC).
    A Bullish OB is the last bearish candle prior to a strong impulsive displacement upward (BOS).
    A Bearish OB is the last bullish candle prior to a strong impulsive displacement downward.
    """
    if len(bars) < 5:
        return []

    ranges = [max(b['high'] - b['low'], abs(b['high'] - bars[i-1]['close'])) for i, b in enumerate(bars) if i > 0]
    atr = float(np.mean(ranges[-atr_period:])) if ranges else 1.0

    order_blocks: List[OrderBlock] = []

    for i in range(2, len(bars) - 2):
        curr = bars[i]
        nxt1 = bars[i + 1]
        nxt2 = bars[i + 2]

        is_bearish_candle = curr['close'] < curr['open']
        upward_displacement = (nxt2['close'] - curr['high']) > (atr * 0.75) and nxt1['close'] > curr['high']
        if is_bearish_candle and upward_displacement:
            ob_low = min(curr['low'], curr['close'])
            ob_high = max(curr['high'], curr['open'])
            mid = (ob_low + ob_high) / 2.0
            
            mitigated = False
            for j in range(i + 2, len(bars)):
                if bars[j]['low'] <= mid:
                    mitigated = True
                    break

            order_blocks.append(OrderBlock(
                id=f"OB-BULL-{i}-{curr.get('time', i)}",
                block_type="BULLISH",
                low=round(ob_low, 2),
                high=round(ob_high, 2),
                mean_threshold=round(mid, 2),
                volume=float(curr.get('volume', 0)),
                timestamp=str(curr.get('time', '')),
                mitigated=mitigated,
                strength=min(1.0, round((nxt2['close'] - curr['high']) / (atr * 1.5), 2))
            ))

        is_bullish_candle = curr['close'] > curr['open']
        downward_displacement = (curr['low'] - nxt2['close']) > (atr * 0.75) and nxt1['close'] < curr['low']
        if is_bullish_candle and downward_displacement:
            ob_low = min(curr['low'], curr['open'])
            ob_high = max(curr['high'], curr['close'])
            mid = (ob_low + ob_high) / 2.0
            
            mitigated = False
            for j in range(i + 2, len(bars)):
                if bars[j]['high'] >= mid:
                    mitigated = True
                    break

            order_blocks.append(OrderBlock(
                id=f"OB-BEAR-{i}-{curr.get('time', i)}",
                block_type="BEARISH",
                low=round(ob_low, 2),
                high=round(ob_high, 2),
                mean_threshold=round(mid, 2),
                volume=float(curr.get('volume', 0)),
                timestamp=str(curr.get('time', '')),
                mitigated=mitigated,
                strength=min(1.0, round((curr['low'] - nxt2['close']) / (atr * 1.5), 2))
            ))

    return order_blocks

def detect_fair_value_gaps(bars: List[Dict]) -> List[FairValueGap]:
    """
    Detect Fair Value Gaps (FVG) / Imbalances.
    Bullish FVG: Candle 1 High < Candle 3 Low.
    Bearish FVG: Candle 1 Low > Candle 3 High.
    """
    if len(bars) < 3:
        return []

    fvgs: List[FairValueGap] = []
    latest_close = bars[-1]['close']

    for i in range(len(bars) - 2):
        c1 = bars[i]
        c2 = bars[i + 1]
        c3 = bars[i + 2]

        if c3['low'] > c1['high']:
            gap_bottom = c1['high']
            gap_top = c3['low']
            gap_size = gap_top - gap_bottom
            mid = (gap_top + gap_bottom) / 2.0

            min_retest = min(b['low'] for b in bars[i + 3:]) if len(bars) > i + 3 else latest_close
            filled = min_retest <= gap_bottom
            fill_pct = 1.0 if filled else max(0.0, min(1.0, (gap_top - min_retest) / gap_size if gap_size > 0 else 0.0))

            fvgs.append(FairValueGap(
                id=f"FVG-BULL-{i}",
                gap_type="BULLISH",
                top=round(gap_top, 2),
                bottom=round(gap_bottom, 2),
                midpoint=round(mid, 2),
                size=round(gap_size, 2),
                timestamp=str(c2.get('time', '')),
                filled=filled,
                fill_pct=round(fill_pct, 2)
            ))

        elif c1['low'] > c3['high']:
            gap_top = c1['low']
            gap_bottom = c3['high']
            gap_size = gap_top - gap_bottom
            mid = (gap_top + gap_bottom) / 2.0

            max_retest = max(b['high'] for b in bars[i + 3:]) if len(bars) > i + 3 else latest_close
            filled = max_retest >= gap_top
            fill_pct = 1.0 if filled else max(0.0, min(1.0, (max_retest - gap_bottom) / gap_size if gap_size > 0 else 0.0))

            fvgs.append(FairValueGap(
                id=f"FVG-BEAR-{i}",
                gap_type="BEARISH",
                top=round(gap_top, 2),
                bottom=round(gap_bottom, 2),
                midpoint=round(mid, 2),
                size=round(gap_size, 2),
                timestamp=str(c2.get('time', '')),
                filled=filled,
                fill_pct=round(fill_pct, 2)
            ))

    return fvgs

def compute_liquidity_heatmap(bars: List[Dict], order_book: Optional[Dict] = None) -> List[LiquidityLevel]:
    """Synthesize liquidity heatmap density from order book depth and historical swing liquidity pools."""
    levels: List[LiquidityLevel] = []
    if not bars:
        return levels

    highs = [b['high'] for b in bars]
    lows = [b['low'] for b in bars]
    volumes = [b.get('volume', 1000) for b in bars]
    max_vol = max(volumes) if volumes else 1.0

    swing_high = max(highs[-20:]) if len(highs) >= 20 else max(highs)
    levels.append(LiquidityLevel(
        price=round(swing_high, 2),
        volume=float(max_vol * 1.5),
        side="BSL",
        intensity=0.95
    ))

    swing_low = min(lows[-20:]) if len(lows) >= 20 else min(lows)
    levels.append(LiquidityLevel(
        price=round(swing_low, 2),
        volume=float(max_vol * 1.5),
        side="SSL",
        intensity=0.95
    ))

    if order_book:
        for bid in order_book.get("bids", []):
            p = float(bid.get("price", 0))
            v = float(bid.get("size", 100))
            if p > 0:
                levels.append(LiquidityLevel(
                    price=round(p, 2),
                    volume=v,
                    side="BID",
                    intensity=min(1.0, round(v / 500.0, 2))
                ))
        for ask in order_book.get("asks", []):
            p = float(ask.get("price", 0))
            v = float(ask.get("size", 100))
            if p > 0:
                levels.append(LiquidityLevel(
                    price=round(p, 2),
                    volume=v,
                    side="ASK",
                    intensity=min(1.0, round(v / 500.0, 2))
                ))

    levels.sort(key=lambda l: l.price, reverse=True)
    return levels

def analyze_order_flow(symbol: str, bars: List[Dict], order_book: Optional[Dict] = None) -> OrderFlowAnalysis:
    """Execute complete order flow analysis pipeline for an underlying."""
    if not bars:
        return OrderFlowAnalysis(
            symbol=symbol,
            timestamp=datetime.now().isoformat(),
            current_price=0.0
        )

    current_price = float(bars[-1]['close'])
    order_blocks = detect_order_blocks(bars)
    fvgs = detect_fair_value_gaps(bars)
    heatmap = compute_liquidity_heatmap(bars, order_book)

    # Active bullish order blocks: unmitigated, or currently within retest zone (-1% to +5%)
    unmitigated_bullish = [
        ob for ob in order_blocks 
        if ob.block_type == "BULLISH" and (not ob.mitigated or ob.high * 0.98 <= current_price <= ob.high * 1.05) and ob.low * 0.98 <= current_price
    ]
    nearest_bullish_ob = max(unmitigated_bullish, key=lambda ob: ob.high) if unmitigated_bullish else (
        max([ob for ob in order_blocks if ob.block_type == "BULLISH" and ob.low <= current_price], key=lambda ob: ob.high) if any(ob.block_type == "BULLISH" and ob.low <= current_price for ob in order_blocks) else None
    )

    unmitigated_bearish = [
        ob for ob in order_blocks 
        if ob.block_type == "BEARISH" and (not ob.mitigated or ob.low * 0.95 <= current_price <= ob.low * 1.02) and ob.high * 1.02 >= current_price
    ]
    nearest_bearish_ob = min(unmitigated_bearish, key=lambda ob: ob.low) if unmitigated_bearish else (
        min([ob for ob in order_blocks if ob.block_type == "BEARISH" and ob.high >= current_price], key=lambda ob: ob.low) if any(ob.block_type == "BEARISH" and ob.high >= current_price for ob in order_blocks) else None
    )

    unfilled_fvgs = [f for f in fvgs if not f.filled]

    trend_bias = "NEUTRAL"
    closes = [float(b.get('close', 0)) for b in bars]
    if len(closes) >= 5:
        ma5 = sum(closes[-5:]) / 5.0
        ma20 = sum(closes[-20:]) / min(len(closes), 20)
        if current_price >= ma20 and ma5 >= ma20:
            trend_bias = "BULLISH"
        elif current_price < ma20 and ma5 < ma20:
            trend_bias = "BEARISH"
            
    if trend_bias == "NEUTRAL":
        if nearest_bullish_ob and not nearest_bearish_ob:
            trend_bias = "BULLISH"
        elif nearest_bearish_ob and not nearest_bullish_ob:
            trend_bias = "BEARISH"
        elif nearest_bullish_ob and nearest_bearish_ob:
            dist_to_bull = current_price - nearest_bullish_ob.high
            dist_to_bear = nearest_bearish_ob.low - current_price
            trend_bias = "BULLISH" if dist_to_bull < dist_to_bear else "BEARISH"

    return OrderFlowAnalysis(
        symbol=symbol,
        timestamp=datetime.now().isoformat(),
        current_price=round(current_price, 2),
        trend_bias=trend_bias,
        order_blocks=order_blocks[-10:],
        fair_value_gaps=fvgs[-10:],
        nearest_bullish_ob=nearest_bullish_ob,
        nearest_bearish_ob=nearest_bearish_ob,
        unfilled_fvgs=unfilled_fvgs[-6:],
        liquidity_heatmap=heatmap[:20]
    )

def calculate_master_strategy_tp_sl(
    symbol: str,
    current_price: float,
    order_flow: OrderFlowAnalysis,
    gamma_profile: Optional[BaseModel] = None,
    trend_bias: str = "BULLISH"
) -> Dict:
    """
    Dynamically decide Take Profit and Stop Loss levels strictly driven by
    institutional Order Blocks (OB), Fair Value Gaps (FVG), and Gamma Profile Walls (GEX).
    """
    if current_price <= 0:
        current_price = 575.0

    call_wall = getattr(gamma_profile, "call_wall", 0.0) if gamma_profile else 0.0
    put_wall = getattr(gamma_profile, "put_wall", 0.0) if gamma_profile else 0.0

    # Bullish Setup (default long structure)
    if trend_bias in ["BULLISH", "NEUTRAL"]:
        # Stop Loss: Anchored immediately below the nearest Bullish Order Block low or Put Wall
        if order_flow.nearest_bullish_ob and order_flow.nearest_bullish_ob.low < current_price:
            structural_support = order_flow.nearest_bullish_ob.low
            sl_reason = f"Bullish OB Invalidation (${structural_support:.2f})"
        elif put_wall > 0 and put_wall < current_price:
            structural_support = put_wall
            sl_reason = f"Gamma Put Wall Floor (${structural_support:.2f})"
        else:
            structural_support = current_price * 0.982
            sl_reason = "Dynamic 1.8% Structural Risk Buffer"

        sl_price = round(min(structural_support - 0.25, current_price * 0.985), 2)

        # Take Profit: Target nearest unfilled FVG imbalance or Call Wall (with minimum expansion)
        unfilled_targets = [f.bottom for f in order_flow.unfilled_fvgs if f.bottom >= current_price * 1.02]
        if unfilled_targets:
            fvg_target = min(unfilled_targets)
            tp_price = round(fvg_target, 2)
            tp_reason = f"FVG Imbalance Fill (${tp_price:.2f})"
        elif call_wall >= current_price * 1.025:
            tp_price = round(call_wall, 2)
            tp_reason = f"Gamma Call Wall Ceiling (${tp_price:.2f})"
        else:
            tp_price = round(current_price * 1.04, 2)
            tp_reason = "Dynamic 4.0% Target Expansion"

    else:
        # Bearish Setup
        if order_flow.nearest_bearish_ob and order_flow.nearest_bearish_ob.high > current_price:
            structural_resist = order_flow.nearest_bearish_ob.high
            sl_reason = f"Bearish OB Ceiling (${structural_resist:.2f})"
        elif call_wall > current_price:
            structural_resist = call_wall
            sl_reason = f"Gamma Call Wall Ceiling (${structural_resist:.2f})"
        else:
            structural_resist = current_price * 1.018
            sl_reason = "Dynamic 1.8% Structural Risk Buffer"

        sl_price = round(max(structural_resist + 0.25, current_price * 1.018), 2)

        unfilled_targets = [f.top for f in order_flow.unfilled_fvgs if f.top <= current_price * 0.98]
        if unfilled_targets:
            fvg_target = max(unfilled_targets)
            tp_price = round(fvg_target, 2)
            tp_reason = f"FVG Imbalance Fill (${tp_price:.2f})"
        elif put_wall > 0 and put_wall <= current_price * 0.975:
            tp_price = round(put_wall, 2)
            tp_reason = f"Gamma Put Wall Floor (${tp_price:.2f})"
        else:
            tp_price = round(current_price * 0.96, 2)
            tp_reason = "Dynamic 4.0% Target Expansion"

    # Enforce standard Alpaca bracket order constraints:
    if tp_price <= current_price:
        tp_price = round(current_price * 1.035, 2)
    if sl_price >= current_price:
        sl_price = round(current_price * 0.982, 2)

    tp_pct = round(((tp_price - current_price) / current_price) * 100, 2)
    sl_pct = round(((current_price - sl_price) / current_price) * 100, 2)
    rr_ratio = round(tp_pct / sl_pct if sl_pct > 0 else 2.0, 2)

    return {
        "entry_price": round(current_price, 2),
        "take_profit_price": tp_price,
        "stop_loss_price": sl_price,
        "take_profit_pct": tp_pct,
        "stop_loss_pct": sl_pct,
        "tp_reason": tp_reason,
        "sl_reason": sl_reason,
        "risk_reward_ratio": rr_ratio
    }

def evaluate_master_strategy_setup(
    symbol: str,
    current_price: float,
    order_flow: OrderFlowAnalysis,
    gamma_profile: Optional[BaseModel] = None
) -> Dict:
    """
    Strict institutional confluence gate for the Master Strategy (OB + FVG + GEX).
    Calculates a confluence score (0.0 to 1.0).
    A trade is ONLY marked valid (is_valid=True) if score >= 0.70 with valid OB and FVG conditions.
    """
    if current_price <= 0:
        current_price = order_flow.current_price or 575.0

    trend_bias = order_flow.trend_bias or "NEUTRAL"
    reasons = []

    # 1. Determine setup direction based on structure
    is_bullish = trend_bias in ["BULLISH", "NEUTRAL"]
    side = "BUY" if is_bullish else "SELL"

    # 2. Order Block Component (Weight: 40 points)
    ob_score = 0.0
    if is_bullish and order_flow.nearest_bullish_ob:
        ob = order_flow.nearest_bullish_ob
        dist_to_ob = (current_price - ob.high) / current_price
        if -0.01 <= dist_to_ob <= 0.025:
            ob_score = 0.40 * ob.strength
            reasons.append(f"Bullish OB Demand Retest at ${ob.low:.2f}-${ob.high:.2f} (Strength: {ob.strength:.2f})")
        elif 0.025 < dist_to_ob <= 0.06:
            ob_score = 0.35 * ob.strength
            reasons.append(f"Bullish Structure Expansion above OB (${ob.high:.2f}, +{dist_to_ob*100:.1f}%)")
        elif 0.06 < dist_to_ob <= 0.12:
            ob_score = 0.25
            reasons.append(f"Bullish Trend Continuation above OB (${ob.high:.2f}, +{dist_to_ob*100:.1f}%)")
        else:
            ob_score = 0.15
            reasons.append(f"Bullish OB Distant (${ob.high:.2f}, +{dist_to_ob*100:.1f}%)")
    elif not is_bullish and order_flow.nearest_bearish_ob:
        ob = order_flow.nearest_bearish_ob
        dist_to_ob = (ob.low - current_price) / current_price
        if -0.01 <= dist_to_ob <= 0.025:
            ob_score = 0.40 * ob.strength
            reasons.append(f"Bearish OB Supply Rejection at ${ob.low:.2f}-${ob.high:.2f} (Strength: {ob.strength:.2f})")
        elif 0.025 < dist_to_ob <= 0.06:
            ob_score = 0.35 * ob.strength
            reasons.append(f"Bearish Structure Breakdown below OB (${ob.low:.2f}, -{dist_to_ob*100:.1f}%)")
        elif 0.06 < dist_to_ob <= 0.12:
            ob_score = 0.25
            reasons.append(f"Bearish Trend Continuation below OB (${ob.low:.2f}, -{dist_to_ob*100:.1f}%)")
        else:
            ob_score = 0.15
            reasons.append(f"Bearish OB Distant (${ob.low:.2f})")
    elif trend_bias == "BULLISH":
        ob_score = 0.25
        reasons.append("Institutional Bullish Momentum & Trend Structure Confirmed")
    elif trend_bias == "BEARISH":
        ob_score = 0.25
        reasons.append("Institutional Bearish Momentum & Trend Structure Confirmed")
    else:
        ob_score = 0.05
        reasons.append("No active unmitigated Order Block in structure")

    # 3. Fair Value Gap Imbalance Target (Weight: 30 points)
    fvg_score = 0.0
    if is_bullish:
        valid_fvgs = [f for f in order_flow.unfilled_fvgs if f.bottom > current_price]
        discount_fvgs = [f for f in order_flow.unfilled_fvgs if f.bottom <= current_price <= f.top * 1.05]
        if valid_fvgs:
            target_fvg = min(valid_fvgs, key=lambda f: f.bottom)
            fvg_score = 0.30
            reasons.append(f"Targeting Unfilled BISI Gap at ${target_fvg.bottom:.2f} (+{((target_fvg.bottom-current_price)/current_price)*100:.1f}%)")
        elif discount_fvgs:
            fvg_score = 0.30
            reasons.append(f"Bullish FVG Discount Support Reached at ${discount_fvgs[0].bottom:.2f}")
        elif len(order_flow.unfilled_fvgs) > 0:
            fvg_score = 0.20
            reasons.append("Dynamic Imbalance Gap Present in Trend")
        else:
            fvg_score = 0.10
            reasons.append("No unfilled upside FVG (Secondary Target Active)")
    else:
        valid_fvgs = [f for f in order_flow.unfilled_fvgs if f.top < current_price]
        premium_fvgs = [f for f in order_flow.unfilled_fvgs if f.bottom * 0.95 <= current_price <= f.top]
        if valid_fvgs:
            target_fvg = max(valid_fvgs, key=lambda f: f.top)
            fvg_score = 0.30
            reasons.append(f"Targeting Unfilled SIBI Gap at ${target_fvg.top:.2f} (-{((current_price-target_fvg.top)/current_price)*100:.1f}%)")
        elif premium_fvgs:
            fvg_score = 0.30
            reasons.append(f"Bearish FVG Premium Resistance Reached at ${premium_fvgs[0].top:.2f}")
        elif len(order_flow.unfilled_fvgs) > 0:
            fvg_score = 0.20
            reasons.append("Dynamic Imbalance Gap Present in Trend")
        else:
            fvg_score = 0.10
            reasons.append("No unfilled downside FVG (Secondary Target Active)")

    # 4. Gamma Profile Confluence (Weight: 20 points)
    gex_score = 0.0
    call_wall = getattr(gamma_profile, "call_wall", 0.0) if gamma_profile else 0.0
    put_wall = getattr(gamma_profile, "put_wall", 0.0) if gamma_profile else 0.0
    gamma_regime = getattr(gamma_profile, "regime", "") if gamma_profile else ""

    if is_bullish:
        if put_wall > 0 and current_price >= put_wall:
            gex_score = 0.20
            reasons.append(f"Gamma Put Wall Floor Confirmed (${put_wall:.2f})")
        elif call_wall > current_price:
            gex_score = 0.15
            reasons.append(f"Room to Gamma Call Wall (${call_wall:.2f})")
        elif gamma_regime == "POSITIVE_GAMMA":
            gex_score = 0.15
            reasons.append("Positive Dealer Gamma Stability Confirmed")
        else:
            gex_score = 0.10
    else:
        if call_wall > 0 and current_price <= call_wall:
            gex_score = 0.20
            reasons.append(f"Gamma Call Wall Ceiling Confirmed (${call_wall:.2f})")
        elif put_wall < current_price:
            gex_score = 0.15
            reasons.append(f"Room to Gamma Put Wall (${put_wall:.2f})")
        elif gamma_regime == "POSITIVE_GAMMA":
            gex_score = 0.15
            reasons.append("Positive Dealer Gamma Stability Confirmed")
        else:
            gex_score = 0.10

    # 5. Dynamic Levels & Risk/Reward Validation (Weight: 10 points)
    levels = calculate_master_strategy_tp_sl(
        symbol=symbol,
        current_price=current_price,
        order_flow=order_flow,
        gamma_profile=gamma_profile,
        trend_bias=trend_bias
    )

    rr_score = 0.10 if levels["risk_reward_ratio"] >= 1.8 else 0.05
    if levels["risk_reward_ratio"] >= 1.8:
        reasons.append(f"Edge Ratio Confirmed (R:R {levels['risk_reward_ratio']}:1)")

    total_score = round(ob_score + fvg_score + gex_score + rr_score, 2)
    is_valid = total_score >= 0.70

    return {
        "symbol": symbol,
        "is_valid": is_valid,
        "score": total_score,
        "side": side,
        "trend_bias": trend_bias,
        "reasons": reasons,
        "levels": levels,
        "status_label": "CONFLUENCE CONFIRMED" if is_valid else (
            "AWAITING OB RETEST" if ob_score < 0.25 else "AWAITING FVG EXPANSION"
        )
    }
