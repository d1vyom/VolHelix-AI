import os
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # Alpaca Configuration
    ALPACA_API_KEY: str = ""
    ALPACA_API_SECRET: str = ""
    ALPACA_BASE_URL: str = "https://paper-api.alpaca.markets"

    # LLM Configuration
    GOOGLE_API_KEY: str = ""
    LLM_MODEL: str = "gemini-3.6-flash"

    # Trading Configuration
    TRADING_INTERVAL_MINUTES: int = 5
    INITIAL_CAPITAL: float = 100000.0
    WATCHED_UNDERLYINGS_STR: str = Field(default="SPY,QQQ,AAPL,NVDA,TSLA", alias="WATCHED_UNDERLYINGS")
    
    @property
    def WATCHED_UNDERLYINGS(self) -> list[str]:
        return [s.strip() for s in self.WATCHED_UNDERLYINGS_STR.split(",")]

    MAX_POSITION_PCT: float = 0.025
    MAX_DAILY_DRAWDOWN: float = 0.03

    # Server Configuration
    API_PORT: int = 8000
    DASHBOARD_PORT: int = 3000
    LOG_LEVEL: str = "INFO"

    # Market Constants (Static)
    MARKET_OPEN: str = "09:30"
    MARKET_CLOSE: str = "16:00"
    MARKET_TIMEZONE: str = "US/Eastern"

    model_config = SettingsConfigDict(
        env_file=os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()
