from datetime import datetime, timezone
try:
    import zoneinfo
    ET_TZ = zoneinfo.ZoneInfo("America/New_York")
except Exception:
    ET_TZ = None

from typing import Dict, Optional
from backend.config import settings
from alpaca.trading.client import TradingClient

import time
_simulation_override: bool = False
_clock_cache: Optional[Dict] = None
_clock_cache_time: float = 0.0
_trading_client: Optional[TradingClient] = None

def _get_trading_client() -> TradingClient:
    global _trading_client
    if _trading_client is None:
        _trading_client = TradingClient(settings.ALPACA_API_KEY, settings.ALPACA_API_SECRET, paper=True)
    return _trading_client

def set_simulation_override(enabled: bool) -> bool:
    global _simulation_override, _clock_cache
    _simulation_override = bool(enabled)
    _clock_cache = None  # invalidate cache immediately on override toggle
    return _simulation_override

def get_simulation_override() -> bool:
    global _simulation_override
    return _simulation_override

def get_market_clock() -> Dict:
    """
    Returns comprehensive market clock status from Alpaca API,
    with robust local Eastern Time fallback and developer simulation override.
    Cached for up to 10 seconds for ultra-low latency (<1ms).
    """
    global _simulation_override, _clock_cache, _clock_cache_time

    # Local Eastern Time calculation
    now_utc = datetime.now(timezone.utc)
    if ET_TZ:
        now_et = now_utc.astimezone(ET_TZ)
    else:
        # Fallback approximation: UTC-4 (EDT)
        from datetime import timedelta
        now_et = now_utc - timedelta(hours=4)

    et_time_str = now_et.strftime("%H:%M:%S ET")

    # Fast cache hit (within 10s)
    now_ts = time.time()
    if _clock_cache is not None and (now_ts - _clock_cache_time < 10.0):
        cached = dict(_clock_cache)
        cached["current_time_et"] = et_time_str
        return cached

    day_of_week = now_et.weekday() # 0 = Monday, 6 = Sunday
    total_minutes = now_et.hour * 60 + now_et.minute
    
    # Standard regular trading hours: 09:30 (570m) to 16:00 (960m) ET, Mon-Fri
    standard_hours_open = (0 <= day_of_week <= 4) and (570 <= total_minutes < 960)

    raw_is_open = standard_hours_open
    next_open = None
    next_close = None

    try:
        client = _get_trading_client()
        clock = client.get_clock()
        raw_is_open = bool(clock.is_open)
        if clock.next_open:
            next_open = clock.next_open.isoformat()
        if clock.next_close:
            next_close = clock.next_close.isoformat()
    except Exception:
        pass

    effective_is_open = True if _simulation_override else raw_is_open

    if _simulation_override:
        reason = "Market Simulation Override Active (Dev/Paper Mode)"
    elif raw_is_open:
        reason = "Regular Trading Session Active (09:30 - 16:00 ET)"
    else:
        reason = "Market is Closed. Regular hours: 09:30 - 16:00 ET, Mon-Fri"

    res = {
        "is_open": effective_is_open,
        "raw_is_open": raw_is_open,
        "simulation_active": _simulation_override,
        "simulation_override": _simulation_override,
        "current_time_et": et_time_str,
        "next_open": next_open,
        "next_close": next_close,
        "reason": reason
    }
    _clock_cache = res
    _clock_cache_time = time.time()
    return res

def is_market_open() -> bool:
    """Returns True if the market is currently open or dev simulation override is enabled."""
    clock_info = get_market_clock()
    return bool(clock_info.get("is_open", False))

check_market_open = get_market_clock
