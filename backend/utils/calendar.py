"""
Economic calendar, earnings dates, and market hours utility.
VolHelix AI Options Orchestrator.
"""

from datetime import datetime, time, date, timedelta
from typing import List, Dict, Optional
import zoneinfo

# 2026 Earnings calendar for watched underlyings
EARNINGS_CALENDAR: Dict[str, List[str]] = {
    "AAPL": ["2026-01-29", "2026-04-30", "2026-07-30", "2026-10-29"],
    "NVDA": ["2026-02-26", "2026-05-28", "2026-08-27", "2026-11-19"],
    "TSLA": ["2026-01-28", "2026-04-22", "2026-07-22", "2026-10-21"],
    "SPY": [],   # ETF, no earnings
    "QQQ": [],   # ETF, no earnings
}

# 2026 FOMC Meeting Announcements
FOMC_DATES: List[str] = [
    "2026-01-28", "2026-03-18", "2026-05-06", "2026-06-17",
    "2026-07-29", "2026-09-16", "2026-11-04", "2026-12-16"
]

# 2026 Major CPI Releases
CPI_DATES: List[str] = [
    "2026-01-14", "2026-02-11", "2026-03-11", "2026-04-14",
    "2026-05-12", "2026-06-10", "2026-07-14", "2026-08-12",
    "2026-09-15", "2026-10-13", "2026-11-12", "2026-12-10"
]

def get_market_tz():
    try:
        return zoneinfo.ZoneInfo("US/Eastern")
    except Exception:
        return None

def is_market_open(dt: Optional[datetime] = None) -> bool:
    """Returns True if US Equity Options market is currently open (9:30 AM - 4:00 PM ET on weekdays)."""
    tz = get_market_tz()
    if dt is None:
        dt = datetime.now(tz) if tz else datetime.now()
    elif tz and dt.tzinfo is None:
        dt = dt.replace(tzinfo=tz)

    # Weekday check (Monday=0, Friday=4)
    if dt.weekday() > 4:
        return False

    market_open = time(9, 30)
    market_close = time(16, 0)
    current_time = dt.time()

    return market_open <= current_time <= market_close

def get_next_opex(current_date: Optional[date] = None) -> date:
    """Get the next standard monthly options expiration date (3rd Friday of the month)."""
    if current_date is None:
        current_date = date.today()

    for i in range(3):
        month = (current_date.month + i - 1) % 12 + 1
        year = current_date.year + (current_date.month + i - 1) // 12

        first_day = date(year, month, 1)
        first_friday = first_day + timedelta(days=(4 - first_day.weekday()) % 7)
        third_friday = first_friday + timedelta(days=14)

        if third_friday >= current_date:
            return third_friday

    return current_date

def get_upcoming_events(underlying: str, days_ahead: int = 7) -> List[Dict[str, str]]:
    """Returns a list of upcoming high-impact economic/earnings events within window."""
    today = date.today()
    events = []

    # Earnings
    for ed in EARNINGS_CALENDAR.get(underlying, []):
        try:
            d = date.fromisoformat(ed)
            days = (d - today).days
            if 0 <= days <= days_ahead:
                events.append({"type": "EARNINGS", "date": ed, "days_until": str(days), "desc": f"Earnings in {days}d"})
        except Exception:
            pass

    # FOMC
    for fd in FOMC_DATES:
        try:
            d = date.fromisoformat(fd)
            days = (d - today).days
            if 0 <= days <= days_ahead:
                events.append({"type": "FOMC", "date": fd, "days_until": str(days), "desc": f"FOMC Rate Decision in {days}d"})
        except Exception:
            pass

    # CPI
    for cd in CPI_DATES:
        try:
            d = date.fromisoformat(cd)
            days = (d - today).days
            if 0 <= days <= days_ahead:
                events.append({"type": "CPI", "date": cd, "days_until": str(days), "desc": f"CPI Inflation Report in {days}d"})
        except Exception:
            pass

    # OPEX
    next_opex = get_next_opex(today)
    days_opex = (next_opex - today).days
    if 0 <= days_opex <= days_ahead:
        events.append({"type": "OPEX", "date": next_opex.isoformat(), "days_until": str(days_opex), "desc": f"Monthly OPEX in {days_opex}d"})

    return sorted(events, key=lambda x: int(x["days_until"]))
