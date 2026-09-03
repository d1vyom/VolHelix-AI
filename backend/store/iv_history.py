"""
IV History Store for storing and retrieving historical IV snapshots.
"""
from backend.engine.iv_calculator import store_iv_snapshot, load_iv_history

class IVHistoryStore:
    async def init_db(self):
        """No-op for JSON file store, ensures async API consistency."""
        pass
        
    async def record_iv(self, symbol: str, iv: float, date: str = None):
        store_iv_snapshot(symbol, iv, date)
        
    def save(self, symbol: str, iv: float, date: str = None):
        store_iv_snapshot(symbol, iv, date)
        
    def get_history(self, symbol: str, days: int = 252):
        return load_iv_history(symbol, days)

iv_history = IVHistoryStore()

save_iv_snapshot = store_iv_snapshot
get_iv_history = load_iv_history

__all__ = ["iv_history", "IVHistoryStore", "save_iv_snapshot", "get_iv_history", "load_iv_history", "store_iv_snapshot"]

