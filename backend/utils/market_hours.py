"""
VolHelix AI - 24/7 Crypto Market Hours Utility.
Crypto markets operate continuously 24 hours a day, 7 days a week, 365 days a year.
"""

from datetime import datetime, timezone
try:
    import zoneinfo
    ET_TZ = zoneinfo.ZoneInfo("America/New_York")
    UTC_TZ = zoneinfo.ZoneInfo("UTC")
except Exception:
    ET_TZ = None
    UTC_TZ = timezone.utc

from typing import Dict, Optional
import time

_simulation_override: bool = False
_clock_cache: Optional[Dict] = None
_clock_cache_time: float = 0.0


def set_simulation_override(enabled: bool) -> bool:
    """Set simulation override status (maintained for dev compatibility)."""
    global _simulation_override, _clock_cache
    _simulation_override = bool(enabled)
    _clock_cache = None
    return _simulation_override


def get_simulation_override() -> bool:
    """Get simulation override status."""
    global _simulation_override
    return _simulation_override


def get_market_clock() -> Dict:
    """
    Returns comprehensive 24/7 crypto market clock status.
    Crypto markets (Binance Spot) never close.
    """
    global _simulation_override, _clock_cache, _clock_cache_time

    now_utc = datetime.now(timezone.utc)
    if ET_TZ:
        now_et = now_utc.astimezone(ET_TZ)
    else:
        from datetime import timedelta
        now_et = now_utc - timedelta(hours=4)

    et_time_str = now_et.strftime("%H:%M:%S ET")
    utc_time_str = now_utc.strftime("%Y-%m-%dT%H:%M:%SZ")

    res = {
        "is_open": True,
        "raw_is_open": True,
        "simulation_active": _simulation_override,
        "simulation_override": _simulation_override,
        "current_time_et": et_time_str,
        "current_time_utc": utc_time_str,
        "next_open": None,
        "next_close": None,
        "market": "CRYPTO_24_7",
        "exchange": "BINANCE",
        "reason": "24/7/365 Continuous Crypto Trading Session Active"
    }
    _clock_cache = res
    _clock_cache_time = time.time()
    return res


def is_market_open() -> bool:
    """Returns True continuously for 24/7 crypto markets."""
    return True


# Backward compatibility alias
check_market_open = get_market_clock
