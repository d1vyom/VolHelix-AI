from datetime import datetime, timedelta
from typing import List, Dict
from backend.config import settings
from backend.models.market import RiskFlags
from backend.mcp.client import BinanceClient
from backend.utils.logger import get_logger

logger = get_logger("event_scanner")

# Global macro calendar events (FOMC, CPI, NFP) impacting crypto markets
FOMC_DATES = [
    "2026-01-28", "2026-03-18", "2026-05-06", "2026-06-17",
    "2026-07-29", "2026-09-16", "2026-11-04", "2026-12-16"
]

CPI_DATES = [
    "2026-01-14", "2026-02-11", "2026-03-11", "2026-04-15",
    "2026-05-13", "2026-06-10", "2026-07-15", "2026-08-12",
    "2026-09-16", "2026-10-14", "2026-11-12", "2026-12-10"
]


class EventScanner:
    """Checks for macroeconomic risks, FOMC decisions, monthly crypto settlements, and market anomalies."""
    
    def __init__(self):
        self.mcp = BinanceClient()
        
    def scan_risks(self, symbol: str) -> RiskFlags:
        """
        Scan for crypto event risks: FOMC, CPI, Deribit monthly options settlement, 24hr volatility spikes.
        """
        clean_sym = symbol.upper()
        logger.info(f"Scanning event risks for {clean_sym}")
        
        today = datetime.now().date()
        events = []
        risk_level = "LOW"
        size_modifier = 1.0
        
        # 1. Check FOMC Meetings
        for fomc in FOMC_DATES:
            fomc_date = datetime.fromisoformat(fomc).date()
            days_until = (fomc_date - today).days
            if 0 <= days_until <= 7:
                events.append(f"FOMC Interest Rate Decision in {days_until} days ({fomc})")
                if days_until <= 1:
                    risk_level = "HIGH"
                    size_modifier = min(size_modifier, 0.5)
                elif days_until <= 4:
                    risk_level = "MEDIUM"
                    size_modifier = min(size_modifier, 0.75)

        # 2. Check CPI Releases
        for cpi in CPI_DATES:
            cpi_date = datetime.fromisoformat(cpi).date()
            days_until = (cpi_date - today).days
            if 0 <= days_until <= 5:
                events.append(f"US CPI Inflation Data in {days_until} days ({cpi})")
                if days_until <= 1:
                    risk_level = "HIGH"
                    size_modifier = min(size_modifier, 0.6)
                elif days_until <= 3:
                    risk_level = "MEDIUM"
                    size_modifier = min(size_modifier, 0.8)

        # 3. Check Crypto Monthly Settlement (Last Friday of month)
        monthly_expiry = self._get_crypto_monthly_expiry(today)
        if monthly_expiry:
            days_until = (monthly_expiry - today).days
            if 0 <= days_until <= 3:
                events.append(f"Major Crypto Derivatives Monthly Expiry in {days_until} days ({monthly_expiry})")
                if days_until <= 1:
                    risk_level = "HIGH"
                    size_modifier = min(size_modifier, 0.7)

        # 4. Check 24hr extreme volatility / liquidation cascade risk
        try:
            ticker = self.mcp.get_24hr_ticker(clean_sym)
            change_pct = abs(float(ticker.get("price_change_pct", 0.0)))
            if change_pct > 10.0:
                events.append(f"High 24h Volatility Spike: {ticker.get('price_change_pct'):+.2f}%")
                risk_level = "HIGH"
                size_modifier = min(size_modifier, 0.5)
            elif change_pct > 5.0:
                events.append(f"Elevated 24h Price Movement: {ticker.get('price_change_pct'):+.2f}%")
                if risk_level == "LOW":
                    risk_level = "MEDIUM"
                    size_modifier = min(size_modifier, 0.8)
        except Exception as e:
            logger.debug(f"Ticker risk check failed for {clean_sym}: {e}")

        return RiskFlags(
            events=events,
            risk_level=risk_level,
            size_modifier=size_modifier
        )
    
    def _get_crypto_monthly_expiry(self, today) -> datetime.date:
        """Deribit/CME crypto options monthly settlement (last Friday of the month)."""
        import calendar
        year = today.year
        month = today.month
        last_day = calendar.monthrange(year, month)[1]
        last_date = datetime(year, month, last_day).date()
        # Friday is weekday 4
        offset = (last_date.weekday() - 4) % 7
        last_friday = last_date - timedelta(days=offset)
        if last_friday >= today:
            return last_friday
        # Next month's last Friday
        next_month = month + 1 if month < 12 else 1
        next_year = year if month < 12 else year + 1
        last_day_next = calendar.monthrange(next_year, next_month)[1]
        last_date_next = datetime(next_year, next_month, last_day_next).date()
        offset_next = (last_date_next.weekday() - 4) % 7
        return last_date_next - timedelta(days=offset_next)
