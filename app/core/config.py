from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    PROJECT_NAME: str = "IBKR Algo Trading"
    
    # Database
    POSTGRES_SERVER: str = "localhost"
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    POSTGRES_DB: str = "ibalgo"
    DATABASE_URL: Optional[str] = None

    # IBKR
    IBKR_HOST: str = "127.0.0.1"
    IBKR_PORT: int = 7497 # 7497 for TWS paper, 4001 for Gateway paper
    IBKR_CLIENT_ID: int = 1

    # Trading
    SYMBOL: str = "GC"
    EXCHANGE: str = "COMEX"
    CURRENCY: str = "USD"
    TIMEFRAME: str = "1 min"
    
    # Strategy Params
    STOP_LOSS_TICKS: int = 20 # 2 points
    TAKE_PROFIT_TICKS: int = 20 # 2 points
    LOOKBACK_BARS: int = 5  # Swing structure lookback
    INTERNAL_LENGTH: int = 5  # Internal structure lookback (for entries)
    ENABLE_CONFLUENCE_FILTER: bool = True  # Filter internal structure by candle bias
    FVG_THRESHOLD_ENABLED: bool = True  # Enable FVG threshold filtering
    
    class Config:
        env_file = ".env"

    def __init__(self, **data):
        super().__init__(**data)
        if not self.DATABASE_URL:
            self.DATABASE_URL = f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_SERVER}/{self.POSTGRES_DB}"

settings = Settings()
