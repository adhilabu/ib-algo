from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, Enum
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime
import enum

Base = declarative_base()

class SignalType(str, enum.Enum):
    BOS_BULLISH = "BOS_BULLISH"
    BOS_BEARISH = "BOS_BEARISH"
    CHOCH_BULLISH = "CHOCH_BULLISH"
    CHOCH_BEARISH = "CHOCH_BEARISH"
    FVG_BULLISH = "FVG_BULLISH"
    FVG_BEARISH = "FVG_BEARISH"
    ORDER_BLOCK_BULLISH = "ORDER_BLOCK_BULLISH"
    ORDER_BLOCK_BEARISH = "ORDER_BLOCK_BEARISH"

class TradeStatus(str, enum.Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"

class Signal(Base):
    __tablename__ = "signals"
    
    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    symbol = Column(String)
    signal_type = Column(String) # SignalType
    price_level = Column(Float)
    extra_metadata = Column(String, nullable=True) # JSON string for extra details

class Trade(Base):
    __tablename__ = "trades"
    
    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String)
    entry_time = Column(DateTime, default=datetime.utcnow)
    entry_price = Column(Float)
    exit_time = Column(DateTime, nullable=True)
    exit_price = Column(Float, nullable=True)
    quantity = Column(Integer)
    direction = Column(String) # LONG or SHORT
    status = Column(String, default=TradeStatus.OPEN) # TradeStatus
    pnl = Column(Float, nullable=True)
    stop_loss = Column(Float)
    take_profit = Column(Float)
    strategy_ref = Column(String, nullable=True) # Reference to the signal that triggered it

class Configuration(Base):
    __tablename__ = "configuration"
    
    key = Column(String, primary_key=True)
    value = Column(String)
    description = Column(String, nullable=True)
