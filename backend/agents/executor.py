from datetime import datetime
from backend.models.trade import TradeProposal, TradeRecord, TradeStatus
from backend.models.risk import RiskGateResult
from backend.mcp.client import AlpacaClient
from backend.utils.logger import get_logger

logger = get_logger("executor")

from typing import Optional

class ExecutionAgent:
    """Translates approved TradeProposals into Alpaca MCP orders."""
    
    def __init__(self, mcp_client: Optional[AlpacaClient] = None):
        self.client = mcp_client or AlpacaClient()
        
    def execute(self, proposal: TradeProposal, risk_result: RiskGateResult) -> TradeRecord:
        """Execute the trade on Alpaca."""
        logger.info(f"Executing approved proposal {proposal.id} for {proposal.underlying}")
        
        # 1. Final pre-flight account check
        account = self.client.get_account()
        if account['buying_power'] < (proposal.max_loss * 100):
            logger.error("Insufficient buying power for execution.")
            return TradeRecord(
                trade_id=proposal.id,
                proposal=proposal,
                status=TradeStatus.CLOSED,
                entry_time=datetime.now().isoformat(),
                realized_pnl=0.0
            )
            
        # 2. Prepare legs for Alpaca multi-leg order
        alpaca_legs = []
        for leg in proposal.legs:
            alpaca_legs.append({
                "symbol": leg.symbol,
                "action": leg.action.upper(),
                "ratio_quantity": 1
            })
        
        # Calculate limit price (midpoint of bid/ask spread for the spread)
        # For credit spreads, we want to receive at least some credit
        if proposal.is_credit:
            # Use net premium as limit price (credit we want to receive)
            limit_price = round(proposal.net_premium, 2)
        else:
            # For debit spreads, use net debit
            limit_price = round(abs(proposal.net_premium), 2)
        
        # Ensure minimum price
        limit_price = max(limit_price, 0.05)
        
        logger.info(f"Placing mleg order: {proposal.strategy_type.value}, limit={limit_price}, legs={len(alpaca_legs)}")
        
        # 3. Place order via Alpaca MCP
        try:
            order_result = self.client.place_multi_leg_order(
                legs=alpaca_legs,
                limit_price=limit_price,
                quantity=1
            )
            
            if order_result.get("status") in ["REJECTED", "ERROR"] or "error" in order_result:
                logger.error(f"Order rejected: {order_result}")
                return TradeRecord(
                    trade_id=proposal.id,
                    proposal=proposal,
                    status=TradeStatus.CLOSED,
                    entry_time=datetime.now().isoformat(),
                    realized_pnl=0.0,
                    mcp_logs=self.client.mcp_logs
                )
                
            logger.info(f"Order placed successfully: {order_result.get('id')}")
            
        except Exception as e:
            logger.error(f"Order placement failed: {e}")
            return TradeRecord(
                trade_id=proposal.id,
                proposal=proposal,
                status=TradeStatus.CLOSED,
                entry_time=datetime.now().isoformat(),
                realized_pnl=0.0,
                mcp_logs=self.client.mcp_logs
            )
        
        # 4. Create TradeRecord
        record = TradeRecord(
            trade_id=proposal.id,
            proposal=proposal,
            status=TradeStatus.OPEN,
            entry_time=datetime.now().isoformat(),
            realized_pnl=0.0,
            mcp_logs=self.client.mcp_logs
        )
        
        # Clear logs from client for the next cycle
        self.client.mcp_logs = []
        
        return record
