import asyncio
import hashlib
from datetime import datetime
from typing import Optional
from backend.models.trade import TradeProposal, TradeRecord, TradeStatus
from backend.models.risk import RiskGateResult
from backend.mcp.client import BinanceClient
from backend.exchange.registry import get_exchange_client
from backend.exchange.schemas import OrderRequest
from backend.exchange.lifecycle import execute_entry
from backend.exchange.execution import OrderExecutionError, OrderOutcomeUnknown


class ExecutionAgent:
    """Execute proposals through the shared durable, freshly risk-gated testnet path."""
    def __init__(self, mcp_client: Optional[BinanceClient] = None):
        self.client = mcp_client

    def execute(self, proposal: TradeProposal, risk_result: RiskGateResult) -> TradeRecord:
        if not risk_result.approved:
            return self._rejected(proposal)
        client=self.client or get_exchange_client(proposal.market)
        client_id='vha-'+hashlib.sha256(proposal.id.encode()).hexdigest()[:32]
        try:
            request=OrderRequest(market=proposal.market,symbol=proposal.symbol,
                side=proposal.side,order_type=proposal.order_type,qty=proposal.qty,
                quote_quantity=proposal.quote_qty,limit_price=proposal.limit_price,
                client_order_id=client_id)
            _,trade=asyncio.run(execute_entry(request,client=client,proposal=proposal))
            return trade
        except OrderOutcomeUnknown:
            # Durable intent remains reserved and visible; never label this canceled.
            raise
        except (OrderExecutionError,ValueError):
            return self._rejected(proposal)

    def _rejected(self,proposal):
        return TradeRecord(trade_id=f'{proposal.market}:{proposal.symbol}:proposal:{proposal.id}',
            market=proposal.market,proposal=proposal,status=TradeStatus.CANCELLED,
            entry_time=datetime.now().isoformat(),exchange_status='NOT_DISPATCHED')
