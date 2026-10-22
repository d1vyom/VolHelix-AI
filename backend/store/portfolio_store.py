from typing import List, Dict
from datetime import datetime
from backend.models.portfolio import PortfolioSnapshot
from backend.models.market import Regime, CryptoAssetBalance
from backend.models.trade import TradeRecord
from collections import deque


class PortfolioStore:
    def __init__(self):
        self.initial_capital = 10000.0
        self.snapshot: PortfolioSnapshot = PortfolioSnapshot(
            timestamp=datetime.now().isoformat(),
            equity=0.0,
            buying_power=0.0,
            daily_risk_available=False,
            daily_pnl=None,
            daily_pnl_pct=None,
            total_pnl=None,
            total_pnl_pct=None,
            open_positions=0,
            open_position_count=0,
            balances={},
            net_delta=0.0,
            net_theta=0.0,
            net_vega=0.0,
            current_regime=Regime.NORMAL,
            exposures={},
            exposure_by_symbol={}
        )
        self.snapshot_history = deque(maxlen=1000)
        
    def update_from_exchange(self, account_data: dict, positions_data: List[dict], current_regime: Regime):
        """Sync the portfolio state from Binance."""
        if account_data.get('error') or account_data.get('status')=='ERROR':
            self.snapshot.account_available=False
            self.snapshot.daily_risk_available=False
            self.snapshot.daily_pnl=self.snapshot.daily_pnl_pct=None
            return
        equity = float(account_data.get('equity', 0.0))
        buying_power = float(account_data.get('buying_power', 0.0))
        total_pnl = account_data.get("total_pnl")
        total_pnl_pct = account_data.get("total_pnl_pct")

        balances_dict = {}
        raw_balances = account_data.get('balances', {})
        for asset, data in raw_balances.items():
            if isinstance(data, dict):
                balances_dict[asset] = CryptoAssetBalance(
                    asset=asset,
                    free=data.get('free', 0.0),
                    locked=data.get('locked', 0.0),
                    total=data.get('total', 0.0),
                    value_usdt=data.get('value_usdt', 0.0)
                )

        exposures = self._calculate_exposures(positions_data)

        self.snapshot = PortfolioSnapshot(
            timestamp=datetime.now().isoformat(),
            equity=equity,
            buying_power=buying_power,
            account_available=True,
            daily_risk_available=account_data.get('daily_pnl') is not None,
            daily_pnl=account_data.get('daily_pnl'),
            daily_pnl_pct=(float(account_data['daily_pnl']) / equity * 100) if equity > 0 and account_data.get('daily_pnl') is not None else None,
            total_pnl=total_pnl,
            total_pnl_pct=total_pnl_pct,
            open_positions=len(positions_data),
            open_position_count=len(positions_data),
            balances=balances_dict,
            net_delta=0.0, 
            net_theta=0.0,
            net_vega=0.0,
            current_regime=current_regime,
            exposures=exposures,
            exposure_by_symbol=exposures
        )
        self.snapshot_history.append(self.snapshot.model_copy(deep=True))

    # Backward compatibility alias
    def update_from_alpaca(self, account_data: dict, positions_data: List[dict], current_regime: Regime):
        self.update_from_exchange(account_data, positions_data, current_regime)
        
    def _calculate_exposures(self, positions_data: List[dict]) -> Dict[str, float]:
        exposures = {}
        for pos in positions_data:
            symbol = pos.get('symbol', 'UNKNOWN')
            val = float(pos.get('market_value', 0.0))
            exposures[symbol] = round(exposures.get(symbol, 0.0) + abs(val), 2)
        return exposures

    def get_snapshot(self) -> PortfolioSnapshot:
        return self.snapshot
        
    def add_position(self, trade: TradeRecord):
        # Update snapshot in memory
        self.snapshot.open_positions += 1
        self.snapshot.open_position_count += 1
        pos_value = trade.proposal.quote_qty or (trade.proposal.qty * trade.proposal.entry_price)
        self.snapshot.buying_power = max(0.0, self.snapshot.buying_power - pos_value)
        self.snapshot_history.append(self.snapshot.model_copy(deep=True))


portfolio_store = PortfolioStore()
