import json
import os
from typing import List, Dict
from datetime import datetime
from backend.models.portfolio import PortfolioSnapshot
from backend.models.market import Regime
from backend.models.trade import TradeRecord, TradeStatus

class PortfolioStore:
    def __init__(self):
        self.snapshot: PortfolioSnapshot = PortfolioSnapshot(
            timestamp=datetime.now().isoformat(),
            equity=100000.0,
            buying_power=100000.0,
            daily_pnl=0.0,
            total_pnl=0.0,
            open_positions=0,
            net_delta=0.0,
            net_theta=0.0,
            net_vega=0.0,
            current_regime=Regime.NORMAL
        )
        self.snapshot_history: List[PortfolioSnapshot] = []
        
    def update_from_alpaca(self, account_data: dict, positions_data: List[dict], current_regime: Regime):
        """Sync the portfolio state from Alpaca."""
        # Note: Delta/Theta/Vega would ideally come from live pricing updates. 
        # Kept at 0.0 for this mock update, handled by pricing engine later.
        self.snapshot = PortfolioSnapshot(
            timestamp=datetime.now().isoformat(),
            equity=account_data.get('equity', 100000.0),
            buying_power=account_data.get('buying_power', 100000.0),
            daily_pnl=0.0, # Computed differently based on start of day equity
            total_pnl=account_data.get('equity', 100000.0) - 100000.0,
            open_positions=len(positions_data),
            net_delta=0.0, 
            net_theta=0.0,
            net_vega=0.0,
            current_regime=current_regime,
            exposures=self._calculate_exposures(positions_data)
        )
        self.snapshot_history.append(self.snapshot)
        
    def _calculate_exposures(self, positions_data: List[dict]) -> Dict[str, float]:
        exposures = {}
        for pos in positions_data:
            symbol = pos.get('symbol', 'UNKNOWN')
            # Assuming option symbol format or mapped base symbol
            base = symbol[:4].strip() if len(symbol) > 4 else symbol
            val = float(pos.get('market_value', 0.0))
            exposures[base] = exposures.get(base, 0.0) + abs(val)
        return exposures

    def get_snapshot(self) -> PortfolioSnapshot:
        return self.snapshot
        
    def add_position(self, trade: TradeRecord):
        # Update snapshot in memory
        self.snapshot.open_positions += 1
        self.snapshot.buying_power -= (trade.proposal.max_loss * 100)
        self.snapshot_history.append(self.snapshot)

portfolio_store = PortfolioStore()
