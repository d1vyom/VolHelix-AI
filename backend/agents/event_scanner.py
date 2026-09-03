from datetime import datetime, timedelta
from typing import List, Dict
from backend.config import settings
from backend.models.market import RiskFlags
from backend.mcp.client import AlpacaClient
from backend.utils.logger import get_logger

logger = get_logger("event_scanner")

# Hardcoded earnings dates for major tickers (2026 estimates)
EARNINGS_CALENDAR = {
    "AAPL": ["2026-01-29", "2026-04-30", "2026-07-30", "2026-10-29"],
    "NVDA": ["2026-02-26", "2026-05-28", "2026-08-27", "2026-11-19"],
    "TSLA": ["2026-01-28", "2026-04-22", "2026-07-22", "2026-10-21"],
    "SPY": [],  # ETF, no earnings
    "QQQ": [],  # ETF, no earnings
}

# FOMC 2026 dates (approximate)
FOMC_DATES = [
    "2026-01-28", "2026-03-18", "2026-05-06", "2026-06-17",
    "2026-07-29", "2026-09-16", "2026-11-04", "2026-12-16"
]

# CPI Release dates (monthly, usually 2nd week)
# NFP Release dates (first Friday of month)

class EventScanner:
    """Checks for upcoming earnings, FOMC, and news sentiment using Alpaca News API."""
    
    def __init__(self):
        self.mcp = AlpacaClient()
        
    def scan_risks(self, underlying: str) -> RiskFlags:
        """
        Scan for event risks: earnings, FOMC, CPI, NFP, news sentiment.
        """
        logger.info(f"Scanning event risks for {underlying}")
        
        today = datetime.now().date()
        events = []
        risk_level = "LOW"
        size_modifier = 1.0
        
        # 1. Check earnings for this underlying
        earnings_dates = EARNINGS_CALENDAR.get(underlying, [])
        for ed in earnings_dates:
            ed_date = datetime.fromisoformat(ed).date()
            days_until = (ed_date - today).days
            if 0 <= days_until <= 7:
                events.append(f"Earnings in {days_until} days ({ed})")
                if days_until <= 2:
                    risk_level = "HIGH"
                    size_modifier = min(size_modifier, 0.3)
                elif days_until <= 5:
                    risk_level = "MEDIUM"
                    size_modifier = min(size_modifier, 0.5)
        
        # 2. Check FOMC
        for fomc in FOMC_DATES:
            fomc_date = datetime.fromisoformat(fomc).date()
            days_until = (fomc_date - today).days
            if 0 <= days_until <= 7:
                events.append(f"FOMC Meeting in {days_until} days ({fomc})")
                if days_until <= 2:
                    risk_level = "HIGH"
                    size_modifier = min(size_modifier, 0.5)
                elif days_until <= 5:
                    risk_level = "MEDIUM"
                    size_modifier = min(size_modifier, 0.7)
        
        # 3. Check monthly OPEX (3rd Friday)
        opex = self._get_next_opex(today)
        if opex:
            days_until = (opex - today).days
            if days_until <= 5:
                events.append(f"Monthly OPEX in {days_until} days ({opex})")
                if days_until <= 2:
                    risk_level = "HIGH"
                    size_modifier = min(size_modifier, 0.5)
        
        # 4. Check news sentiment via Alpaca
        try:
            news = self._get_news_sentiment(underlying)
            if news["sentiment"] < -0.3:
                events.append(f"Negative news sentiment: {news['sentiment']:.2f}")
                risk_level = "MEDIUM"
                size_modifier = min(size_modifier, 0.7)
            elif news["sentiment"] > 0.3:
                events.append(f"Positive news sentiment: {news['sentiment']:.2f}")
        except Exception as e:
            logger.warning(f"News sentiment fetch failed for {underlying}: {e}")
        
        return RiskFlags(
            events=events,
            risk_level=risk_level,
            size_modifier=size_modifier
        )
    
    def _get_next_opex(self, today) -> datetime:
        """Get next monthly OPEX date (3rd Friday of month)."""
        # Find next 3rd Friday
        for i in range(2):
            year = today.year + (today.month + i) // 12
            month = (today.month + i - 1) % 12 + 1
            
            # 1st day of month
            first_day = datetime(year, month, 1)
            # First Friday
            first_friday = first_day + timedelta(days=(4 - first_day.weekday()) % 7)
            # Third Friday
            third_friday = first_friday + timedelta(days=14)
            
            if third_friday.date() >= today:
                return third_friday.date()
        return None
    
    def _get_news_sentiment(self, underlying: str) -> Dict:
        """Fetch news from Alpaca and compute sentiment."""
        # Use Alpaca news API
        try:
            # Alpaca news endpoint - using the SDK
            from alpaca.data.requests import NewsRequest
            from alpaca.data.historical.news import NewsHistoricalDataClient
            
            news_client = NewsHistoricalDataClient(
                settings.ALPACA_API_KEY, 
                settings.ALPACA_API_SECRET
            )
            
            req = NewsRequest(
                symbols=[underlying],
                start=datetime.now() - timedelta(days=1),
                limit=20
            )
            articles = news_client.get_news(req)
            
            if not articles or not hasattr(articles, '__iter__') or len(list(articles)) == 0:
                return {"sentiment": 0.0, "articles": 0}
            
            # Simple sentiment scoring based on keywords
            positive_words = ["beat", "surge", "rally", "growth", "profit", "upgrade", "bullish", "strong", "record", "high"]
            negative_words = ["miss", "drop", "fall", "loss", "downgrade", "bearish", "weak", "low", "cut", "warn"]
            
            total_score = 0
            count = 0
            for article in articles:
                if hasattr(article, 'headline'):
                    text = article.headline.lower()
                    for word in positive_words:
                        if word in text:
                            total_score += 1
                    for word in negative_words:
                        if word in text:
                            total_score -= 1
                    count += 1
            
            avg_sentiment = total_score / max(count, 1) / 5.0  # Normalize to -1 to 1
            return {"sentiment": max(-1.0, min(1.0, avg_sentiment)), "articles": count}
        except Exception as e:
            logger.debug(f"News fetch error (may not have news access): {e}")
            return {"sentiment": 0.0, "articles": 0}
