"""
VolHelix AI - 24/7 Crypto Market Hours Utility.

Crypto markets (Binance Spot) trade continuously, so there is no session gate and
no override: execution is always permitted. The clock below is informational only
(session timestamps for the UI).
"""

from datetime import datetime, timedelta, timezone
from typing import Dict

try:
    import zoneinfo
    ET_TZ = zoneinfo.ZoneInfo("America/New_York")
except Exception:
    ET_TZ = None


def get_market_clock() -> Dict:
    """
    Return the informational 24/7 crypto session clock.

    Returns:
        Dict: Session metadata. ``is_open`` is always True because Binance Spot
        trades around the clock, so execution is never gated on market hours.
    """
    now_utc = datetime.now(timezone.utc)
    if ET_TZ:
        now_et = now_utc.astimezone(ET_TZ)
    else:
        now_et = now_utc - timedelta(hours=4)

    return {
        "is_open": True,
        "current_time_et": now_et.strftime("%H:%M:%S ET"),
        "current_time_utc": now_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "next_open": None,
        "next_close": None,
        "market": "CRYPTO_24_7",
        "exchange": "BINANCE",
        "reason": "24/7/365 Continuous Crypto Trading Session Active",
    }


def is_market_open() -> bool:
    """Returns True continuously for 24/7 crypto markets."""
    return True


# Backward compatibility alias
check_market_open = get_market_clock
