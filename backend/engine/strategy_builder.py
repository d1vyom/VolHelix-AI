import uuid
from typing import Optional
from backend.models.market import OptionLeg, StrategyType
from backend.models.trade import TradeProposal

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
    take_profit: Optional[float] = None,
    stop_loss: Optional[float] = None
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
