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

    # ── Order Flow Engine ──
    FLOW_ENABLED: bool = True
    FLOW_SYMBOLS_STR: str = Field(
        default="",
        alias="FLOW_SYMBOLS"
    )
    FLOW_WS_BASE_URL: str = "wss://stream.binance.com:9443"
    FLOW_DEPTH_LEVELS: int = 20
    FLOW_DEPTH_SNAPSHOT_LIMIT: int = 1000
    FLOW_USE_DIFF_DEPTH: bool = True
    FLOW_TICK_GROUP_MULTIPLIER: float = 1.0
    FLOW_FOOTPRINT_INTERVALS_STR: str = Field(
        default="1m,5m,15m",
        alias="FLOW_FOOTPRINT_INTERVALS"
    )
    FLOW_FOOTPRINT_BARS: int = 240
    FLOW_TAPE_BUFFER: int = 2000
    FLOW_TRADE_BUFFER: int = 50000
    FLOW_HEATMAP_WINDOW_SEC: int = 600
    FLOW_HEATMAP_BIN_MS: int = 1000
    FLOW_IMBALANCE_RATIO: float = 3.0
    FLOW_IMBALANCE_MIN_VOLUME: float = 0.0
    FLOW_STACKED_IMBALANCE_MIN: int = 3
    FLOW_VALUE_AREA_PCT: float = 0.70
    FLOW_WHALE_NOTIONAL_USD: float = 100000.0
    FLOW_LARGE_PRINT_PERCENTILE: float = 0.99
    FLOW_WALL_MULTIPLIER: float = 5.0
    FLOW_BROADCAST_HZ: float = 4.0
    FLOW_TAPE_BROADCAST_HZ: float = 10.0
    FLOW_MAX_RECONNECT_BACKOFF_SEC: int = 60
    FLOW_CONFLUENCE_ENABLED: bool = False
    FLOW_CONFLUENCE_WEIGHT: float = 0.25
    FLOW_PERSIST_BARS: bool = False

    @property
    def FLOW_SYMBOLS(self) -> list[str]:
        if self.FLOW_SYMBOLS_STR and self.FLOW_SYMBOLS_STR.strip():
            return [s.strip().upper() for s in self.FLOW_SYMBOLS_STR.split(",") if s.strip()]
        return self.WATCHED_SYMBOLS

    @property
    def FLOW_FOOTPRINT_INTERVALS(self) -> list[str]:
        return [i.strip() for i in self.FLOW_FOOTPRINT_INTERVALS_STR.split(",") if i.strip()]

    model_config = SettingsConfigDict(
        env_file=os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()
