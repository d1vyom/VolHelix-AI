"""
Economic calendar, crypto events, settlement dates, and 24/7 market hours utility.
VolHelix AI Crypto Trading Engine.
"""

from datetime import datetime, time, date, timedelta
from typing import List, Dict, Optional
import zoneinfo

# 2026 Crypto Major Events Calendar (Upgrades, Halvings, Hard Forks)
CRYPTO_EVENTS_CALENDAR: Dict[str, List[Dict[str, str]]] = {
    "BTCUSDT": [
        {"date": "2026-03-31", "desc": "Bitcoin Core Major Client Upgrade Window"},
        {"date": "2026-10-15", "desc": "Bitcoin Layer-2 Interoperability Summit & Releases"}
    ],
    "ETHUSDT": [
        {"date": "2026-04-15", "desc": "Ethereum Protocol Upgrade Window (Pectra Phase 2)"},
        {"date": "2026-11-20", "desc": "Ethereum Devcon & Consensus Layer Hardfork Window"}
    ],
    "SOLUSDT": [
        {"date": "2026-05-10", "desc": "Solana Firedancer Full Mainnet Validator Rollout"},
        {"date": "2026-09-25", "desc": "Solana Breakpoint Annual Developer Conference"}
    ],
    "BNBUSDT": [
        {"date": "2026-06-30", "desc": "BNB Chain Quarterly Auto-Burn Event"},
        {"date": "2026-12-31", "desc": "BNB Chain Quarterly Auto-Burn Event"}
    ],
    "XRPUSDT": [
        {"date": "2026-05-20", "desc": "XRPL EVM Sidechain Protocol Mainnet Launch"},
        {"date": "2026-10-10", "desc": "Ripple Swell Global Institutional Conference"}
    ]
}

# 2026 FOMC Meeting Announcements (Macro liquidity impact on Crypto)
FOMC_DATES: List[str] = [
    "2026-01-28", "2026-03-18", "2026-05-06", "2026-06-17",
    "2026-07-29", "2026-09-16", "2026-11-04", "2026-12-16"
]

# 2026 Major CPI Releases (Inflation data directly impacts crypto flows)
CPI_DATES: List[str] = [
    "2026-01-14", "2026-02-11", "2026-03-11", "2026-04-14",
    "2026-05-12", "2026-06-10", "2026-07-14", "2026-08-12",
    "2026-09-15", "2026-10-13", "2026-11-12", "2026-12-10"
]


def get_market_tz():
    try:
        return zoneinfo.ZoneInfo("UTC")
    except Exception:
        return None


def is_market_open(dt: Optional[datetime] = None) -> bool:
    """Returns True continuously for 24/7/365 crypto markets."""
    return True


def get_next_crypto_expiry(current_date: Optional[date] = None) -> date:
    """
    Get the next monthly crypto options/futures settlement date
    (Last Friday of the month at 08:00 UTC).
    """
    if current_date is None:
        current_date = date.today()

    for i in range(3):
        month = (current_date.month + i - 1) % 12 + 1
        year = current_date.year + (current_date.month + i - 1) // 12

        # Find last day of month
        if month == 12:
            last_day = date(year, 12, 31)
        else:
            last_day = date(year, month + 1, 1) - timedelta(days=1)

        # Last Friday
        offset = (last_day.weekday() - 4) % 7
        last_friday = last_day - timedelta(days=offset)

        if last_friday >= current_date:
            return last_friday

    return current_date


# Backward compatibility alias
get_next_opex = get_next_crypto_expiry


def get_upcoming_events(symbol: str, days_ahead: int = 14) -> List[Dict[str, str]]:
    """Returns a list of upcoming high-impact crypto/macro events within window."""
    today = date.today()
    events = []
    clean_sym = symbol.upper().replace("/", "")

    # Crypto Protocol Events
    for ev in CRYPTO_EVENTS_CALENDAR.get(clean_sym, []):
        try:
            d = date.fromisoformat(ev["date"])
            days = (d - today).days
            if 0 <= days <= days_ahead:
                events.append({
                    "type": "PROTOCOL",
                    "date": ev["date"],
                    "days_until": str(days),
                    "desc": f"{ev['desc']} (in {days}d)"
                })
        except Exception:
            pass

    # FOMC
    for fd in FOMC_DATES:
        try:
            d = date.fromisoformat(fd)
            days = (d - today).days
            if 0 <= days <= days_ahead:
                events.append({
                    "type": "FOMC",
                    "date": fd,
                    "days_until": str(days),
                    "desc": f"FOMC Rate Decision in {days}d"
                })
        except Exception:
            pass

    # CPI
    for cd in CPI_DATES:
        try:
            d = date.fromisoformat(cd)
            days = (d - today).days
            if 0 <= days <= days_ahead:
                events.append({
                    "type": "CPI",
                    "date": cd,
                    "days_until": str(days),
                    "desc": f"CPI Inflation Report in {days}d"
                })
        except Exception:
            pass

    # Monthly Settlement
    next_expiry = get_next_crypto_expiry(today)
    days_exp = (next_expiry - today).days
    if 0 <= days_exp <= days_ahead:
        events.append({
            "type": "SETTLEMENT",
            "date": next_expiry.isoformat(),
            "days_until": str(days_exp),
            "desc": f"Crypto Monthly Expiry in {days_exp}d"
        })

    return sorted(events, key=lambda x: int(x["days_until"]))
