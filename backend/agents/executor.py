from datetime import datetime
from typing import Optional
from backend.models.trade import TradeProposal, TradeRecord, TradeStatus
from backend.models.risk import RiskGateResult
from backend.mcp.client import BinanceClient
from backend.utils.logger import get_logger

logger = get_logger("executor")


class ExecutionAgent:
    """Translates approved TradeProposals into Binance Spot Testnet orders."""
    
    def __init__(self, mcp_client: Optional[BinanceClient] = None):
        self.client = mcp_client or BinanceClient()
        
    def execute(self, proposal: TradeProposal, risk_result: RiskGateResult) -> TradeRecord:
        """Execute the spot trade on Binance Spot Testnet."""
        symbol = (proposal.symbol or proposal.underlying or "BTCUSDT").upper()
        side = (proposal.side or "BUY").upper()
        order_type = (proposal.order_type or "MARKET").upper()
        
        logger.info(f"Executing approved {side} proposal {proposal.id} for {symbol} ({order_type})")
        
        # 1. Pre-flight account check
        account = self.client.get_account()
        buying_power = account.get("buying_power", 0.0)
        
        # Determine order sizing
        qty = proposal.qty if proposal.qty > 0 else None
        quote_qty = proposal.quote_qty
        
        if not qty and not quote_qty:
            quote_qty = 100.0  # Default safe position size in USDT
            
        if side == "BUY" and quote_qty and buying_power < quote_qty:
            logger.error(f"Insufficient buying power (${buying_power:.2f} < ${quote_qty:.2f})")
            return TradeRecord(
                trade_id=proposal.id,
                proposal=proposal,
                status=TradeStatus.CANCELLED,
                entry_time=datetime.now().isoformat(),
                realized_pnl=0.0
            )
            
        # 2. Place spot order via BinanceClient
        try:
            order_result = self.client.place_order(
                symbol=symbol,
                side=side,
                order_type=order_type,
                quantity=qty if not quote_qty else None,
                quote_quantity=quote_qty,
                price=proposal.limit_price if order_type == "LIMIT" else None
            )
            
            if order_result.get("status") in ["REJECTED", "ERROR"] or "error" in order_result:
                logger.error(f"Order rejected on testnet: {order_result}")
                return TradeRecord(
                    trade_id=proposal.id,
                    proposal=proposal,
                    status=TradeStatus.CANCELLED,
                    entry_time=datetime.now().isoformat(),
                    realized_pnl=0.0,
                    mcp_logs=list(self.client.call_logs)
                )
                
            binance_order_id = str(order_result.get("order_id", ""))
            fill_price = float(order_result.get("price") or proposal.entry_price or 0.0)
            if fill_price <= 0 and order_result.get("fills"):
                fill_price = float(order_result["fills"][0].get("price", 0.0))
            if fill_price <= 0:
                fill_price = self.client.get_price(symbol).get("price", 0.0)
                
            logger.info(f"Order placed successfully on Binance Testnet: order_id={binance_order_id}, price={fill_price}")
            
        except Exception as e:
            logger.error(f"Binance order placement failed: {e}")
            return TradeRecord(
                trade_id=proposal.id,
                proposal=proposal,
                status=TradeStatus.CANCELLED,
                entry_time=datetime.now().isoformat(),
                realized_pnl=0.0,
                mcp_logs=list(self.client.call_logs)
            )
        
        # 3. Create and return TradeRecord
        record = TradeRecord(
            trade_id=proposal.id,
            proposal=proposal,
            status=TradeStatus.OPEN,
            entry_time=datetime.now().isoformat(),
            entry_price=fill_price,
            take_profit_price=proposal.take_profit,
            stop_loss_price=proposal.stop_loss,
            binance_order_id=binance_order_id,
            realized_pnl=0.0,
            mcp_logs=list(self.client.call_logs)
        )
        
        return record
