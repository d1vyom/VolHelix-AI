import uuid
from backend.models.market import OptionLeg, StrategyType
from backend.models.trade import TradeProposal

def build_bull_put_spread(underlying: str, short_put: OptionLeg, long_put: OptionLeg, expiry: str, dte: int, thesis: str) -> TradeProposal:
    """
    Constructs a Bull Put Spread (Credit Spread).
    Sell short_put (higher strike), Buy long_put (lower strike).
    """
    assert short_put.strike > long_put.strike, "Short put strike must be higher than long put strike"
    assert short_put.contract_type == 'PUT' and long_put.contract_type == 'PUT'
    
    net_credit = short_put.premium - long_put.premium
    spread_width = short_put.strike - long_put.strike
    max_loss = spread_width - net_credit
    
    net_delta = short_put.delta + long_put.delta
    net_theta = short_put.theta + long_put.theta
    net_vega = short_put.vega + long_put.vega
    
    breakeven = short_put.strike - net_credit
    
    return TradeProposal(
        id=str(uuid.uuid4()),
        underlying=underlying,
        strategy_type=StrategyType.BULL_PUT_SPREAD,
        legs=[short_put, long_put],
        is_credit=True,
        net_premium=net_credit,
        max_profit=net_credit,
        max_loss=max_loss,
        breakevens=[breakeven],
        net_delta=net_delta,
        net_theta=net_theta,
        net_vega=net_vega,
        dte=dte,
        ev=0.0, # Filled by agent
        thesis=thesis
    )

def build_bear_call_spread(underlying: str, short_call: OptionLeg, long_call: OptionLeg, expiry: str, dte: int, thesis: str) -> TradeProposal:
    """
    Constructs a Bear Call Spread (Credit Spread).
    Sell short_call (lower strike), Buy long_call (higher strike).
    """
    assert short_call.strike < long_call.strike, "Short call strike must be lower than long call strike"
    assert short_call.contract_type == 'CALL' and long_call.contract_type == 'CALL'
    
    net_credit = short_call.premium - long_call.premium
    spread_width = long_call.strike - short_call.strike
    max_loss = spread_width - net_credit
    
    net_delta = short_call.delta + long_call.delta
    net_theta = short_call.theta + long_call.theta
    net_vega = short_call.vega + long_call.vega
    
    breakeven = short_call.strike + net_credit
    
    return TradeProposal(
        id=str(uuid.uuid4()),
        underlying=underlying,
        strategy_type=StrategyType.BEAR_CALL_SPREAD,
        legs=[short_call, long_call],
        is_credit=True,
        net_premium=net_credit,
        max_profit=net_credit,
        max_loss=max_loss,
        breakevens=[breakeven],
        net_delta=net_delta,
        net_theta=net_theta,
        net_vega=net_vega,
        dte=dte,
        ev=0.0,
        thesis=thesis
    )

def build_iron_condor(underlying: str, short_put: OptionLeg, long_put: OptionLeg, short_call: OptionLeg, long_call: OptionLeg, expiry: str, dte: int, thesis: str) -> TradeProposal:
    """Constructs an Iron Condor."""
    # Basically a Bull Put + Bear Call
    assert short_put.strike > long_put.strike
    assert short_call.strike < long_call.strike
    assert short_put.strike < short_call.strike
    
    net_credit = (short_put.premium - long_put.premium) + (short_call.premium - long_call.premium)
    put_width = short_put.strike - long_put.strike
    call_width = long_call.strike - short_call.strike
    max_loss = max(put_width, call_width) - net_credit
    
    net_delta = short_put.delta + long_put.delta + short_call.delta + long_call.delta
    net_theta = short_put.theta + long_put.theta + short_call.theta + long_call.theta
    net_vega = short_put.vega + long_put.vega + short_call.vega + long_call.vega
    
    lower_breakeven = short_put.strike - net_credit
    upper_breakeven = short_call.strike + net_credit
    
    return TradeProposal(
        id=str(uuid.uuid4()),
        underlying=underlying,
        strategy_type=StrategyType.IRON_CONDOR,
        legs=[short_put, long_put, short_call, long_call],
        is_credit=True,
        net_premium=net_credit,
        max_profit=net_credit,
        max_loss=max_loss,
        breakevens=[lower_breakeven, upper_breakeven],
        net_delta=net_delta,
        net_theta=net_theta,
        net_vega=net_vega,
        dte=dte,
        ev=0.0,
        thesis=thesis
    )

def build_long_straddle(underlying: str, call_leg: OptionLeg, put_leg: OptionLeg, expiry: str, dte: int, thesis: str) -> TradeProposal:
    """Constructs a Long Straddle (Debit Strategy). Buy ATM Call + Buy ATM Put."""
    assert call_leg.strike == put_leg.strike, "Straddle call and put strikes must match"
    assert call_leg.contract_type == 'CALL' and put_leg.contract_type == 'PUT'
    
    net_debit = call_leg.premium + put_leg.premium
    max_loss = net_debit
    max_profit = 999999.0  # Theoretically unlimited
    
    net_delta = call_leg.delta + put_leg.delta
    net_theta = call_leg.theta + put_leg.theta
    net_vega = call_leg.vega + put_leg.vega
    
    lower_be = call_leg.strike - net_debit
    upper_be = call_leg.strike + net_debit
    
    return TradeProposal(
        id=str(uuid.uuid4()),
        underlying=underlying,
        strategy_type=StrategyType.LONG_STRADDLE,
        legs=[call_leg, put_leg],
        is_credit=False,
        net_premium=-net_debit,
        max_profit=max_profit,
        max_loss=max_loss,
        breakevens=[lower_be, upper_be],
        net_delta=net_delta,
        net_theta=net_theta,
        net_vega=net_vega,
        dte=dte,
        ev=0.0,
        thesis=thesis
    )

def build_calendar_spread(underlying: str, short_leg: OptionLeg, long_leg: OptionLeg, expiry: str, dte: int, thesis: str) -> TradeProposal:
    """Constructs a Calendar Spread (Debit Strategy). Sell front-month, Buy back-month."""
    assert short_leg.strike == long_leg.strike, "Calendar strikes must match"
    
    net_debit = long_leg.premium - short_leg.premium
    max_loss = max(0.01, net_debit)
    max_profit = net_debit * 1.5  # Typical max profit estimate at front expiry
    
    net_delta = short_leg.delta + long_leg.delta
    net_theta = short_leg.theta + long_leg.theta
    net_vega = short_leg.vega + long_leg.vega
    
    lower_be = short_leg.strike - net_debit
    upper_be = short_leg.strike + net_debit
    
    return TradeProposal(
        id=str(uuid.uuid4()),
        underlying=underlying,
        strategy_type=StrategyType.CALENDAR_SPREAD,
        legs=[short_leg, long_leg],
        is_credit=False,
        net_premium=-net_debit,
        max_profit=max_profit,
        max_loss=max_loss,
        breakevens=[lower_be, upper_be],
        net_delta=net_delta,
        net_theta=net_theta,
        net_vega=net_vega,
        dte=dte,
        ev=0.0,
        thesis=thesis
    )

def build_master_order_flow_strategy(
    underlying: str,
    legs: list[OptionLeg],
    is_credit: bool,
    net_premium: float,
    max_profit: float,
    max_loss: float,
    breakevens: list[float],
    dte: int,
    thesis: str,
    take_profit: float = None,
    stop_loss: float = None
) -> TradeProposal:
    """
    Constructs the VolHelix Master Order Flow Strategy.
    Anchors options spread strikes strictly beyond institutional Order Blocks (OB),
    Fair Value Gaps (FVG), and Gamma Profile Walls (Put Wall support / Call Wall resistance).
    """
    net_delta = sum(l.delta for l in legs)
    net_theta = sum(l.theta for l in legs)
    net_vega = sum(l.vega for l in legs)

    return TradeProposal(
        id=str(uuid.uuid4()),
        underlying=underlying,
        strategy_type=StrategyType.MASTER_ORDER_FLOW,
        legs=legs,
        is_credit=is_credit,
        net_premium=round(net_premium, 2),
        max_profit=round(max_profit, 2),
        max_loss=round(max_loss, 2),
        breakevens=[round(b, 2) for b in breakevens],
        net_delta=round(net_delta, 3),
        net_theta=round(net_theta, 3),
        net_vega=round(net_vega, 3),
        dte=dte,
        ev=0.0,
        thesis=thesis,
        take_profit=take_profit,
        stop_loss=stop_loss
    )

