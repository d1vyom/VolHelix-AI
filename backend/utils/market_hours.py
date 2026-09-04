from datetime import datetime, timezone
try:
    import zoneinfo
    ET_TZ = zoneinfo.ZoneInfo("America/New_York")
except Exception:
    ET_TZ = None

from typing import Dict
from backend.config import settings
from alpaca.trading.client import TradingClient

_simulation_override: bool = False

def set_simulation_override(enabled: bool) -> bool:
    global _simulation_override
    _simulation_override = bool(enabled)
    return _simulation_override

def get_simulation_override() -> bool:
    global _simulation_override
    return _simulation_override

def get_market_clock() -> Dict:
    """
    Returns comprehensive market clock status from Alpaca API,
    with robust local Eastern Time fallback and developer simulation override.
    """
    global _simulation_override

    # Local Eastern Time calculation
    now_utc = datetime.now(timezone.utc)
    if ET_TZ:
        now_et = now_utc.astimezone(ET_TZ)
    else:
        # Fallback approximation: UTC-4 (EDT)
        from datetime import timedelta
        now_et = now_utc - timedelta(hours=4)

    et_time_str = now_et.strftime("%H:%M:%S ET")
    day_of_week = now_et.weekday() # 0 = Monday, 6 = Sunday
    total_minutes = now_et.hour * 60 + now_et.minute
    
    # Standard regular trading hours: 09:30 (570m) to 16:00 (960m) ET, Mon-Fri
    standard_hours_open = (0 <= day_of_week <= 4) and (570 <= total_minutes < 960)

    raw_is_open = standard_hours_open
    next_open = None
    next_close = None

    try:
        client = TradingClient(settings.ALPACA_API_KEY, settings.ALPACA_API_SECRET, paper=True)
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

    return {
        "is_open": effective_is_open,
        "raw_is_open": raw_is_open,
        "simulation_active": _simulation_override,
        "current_time_et": et_time_str,
        "next_open": next_open,
        "next_close": next_close,
        "reason": reason
    }

def is_market_open() -> bool:
    """Returns True if the market is currently open or dev simulation override is enabled."""
    clock_info = get_market_clock()
    return bool(clock_info.get("is_open", False))

check_market_open = get_market_clock
