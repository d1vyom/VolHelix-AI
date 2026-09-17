import os
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # Binance Configuration
    BINANCE_API_KEY: str = ""
    BINANCE_API_SECRET: str = ""
    BINANCE_BASE_URL: str = "https://testnet.binance.vision"
    BINANCE_USE_TESTNET: bool = True

    # LLM Configuration
    GOOGLE_API_KEY: str = ""
    LLM_MODEL: str = "gemini-3.6-flash"

    # Trading Configuration
    TRADING_INTERVAL_MINUTES: int = 5
    INITIAL_CAPITAL: float = 10000.0
    WATCHED_SYMBOLS_STR: str = Field(
        default="BTCUSDT,ETHUSDT,SOLUSDT,BNBUSDT,XRPUSDT",
        alias="WATCHED_SYMBOLS"
    )

    @property
    def WATCHED_SYMBOLS(self) -> list[str]:
        return [s.strip() for s in self.WATCHED_SYMBOLS_STR.split(",")]

    # Backward compatibility alias during progressive migration
    @property
    def WATCHED_UNDERLYINGS(self) -> list[str]:
        return self.WATCHED_SYMBOLS

    MAX_POSITION_PCT: float = 0.025
    MAX_DAILY_DRAWDOWN: float = 0.03

    # Server Configuration
    API_PORT: int = 8000
    DASHBOARD_PORT: int = 3000
    LOG_LEVEL: str = "INFO"

    # Crypto Market Constants (24/7 — no market hours restriction)
    MARKET_IS_ALWAYS_OPEN: bool = True

    model_config = SettingsConfigDict(
        env_file=os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()
