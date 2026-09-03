from typing import List, Tuple
from backend.models.trade import TradeRecord, TradeStatus
from backend.utils.logger import get_logger

logger = get_logger("exit_manager")

class ExitManager:
    """Monitors open positions for Stop-Loss and Take-Profit conditions."""
    
    def __init__(self):
        # -50% of credit received is stop loss, +60% of max profit is take profit
        self.STOP_LOSS_PCT = -0.50 
        self.TAKE_PROFIT_PCT = 0.60
        
    def check_exits(self, open_positions: List[TradeRecord], current_prices: dict) -> List[Tuple[str, TradeStatus]]:
        """
        Evaluates open positions against current market prices.
        current_prices: dict mapping trade_id -> current realized/unrealized P&L
        Returns a list of (trade_id, exit_reason) for positions that should be closed.
        """
        exits = []
        for position in open_positions:
            if position.status != TradeStatus.OPEN:
                continue
                
            trade_id = position.trade_id
            current_pnl = current_prices.get(trade_id, 0.0)
            
            max_profit = position.proposal.max_profit * 100
            credit_received = position.proposal.net_premium * 100
            
            # For credit spreads, max loss is bounded, but we stop out early
            stop_loss_amount = credit_received * self.STOP_LOSS_PCT
            take_profit_amount = max_profit * self.TAKE_PROFIT_PCT
            
            if current_pnl <= stop_loss_amount:
                logger.warning(f"Trade {trade_id} hit STOP LOSS: {current_pnl:.2f} <= {stop_loss_amount:.2f}")
                exits.append((trade_id, TradeStatus.STOPPED_OUT))
                
            elif current_pnl >= take_profit_amount:
                logger.info(f"Trade {trade_id} hit TAKE PROFIT: {current_pnl:.2f} >= {take_profit_amount:.2f}")
                exits.append((trade_id, TradeStatus.TAKE_PROFIT))
                
        return exits
