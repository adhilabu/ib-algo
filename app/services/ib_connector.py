import asyncio
from ib_async import *
from app.core.config import settings
import logging
import pandas as pd
from datetime import datetime

logger = logging.getLogger(__name__)

class IBConnector:
    def __init__(self):
        self.ib = None  # Will be created lazily in the event loop
        self.connected = False
        self.contract = None
        self.bars = []
        self.df = pd.DataFrame()
        self.continuous_contract = None
        self.tradeable_contract = None
        
    async def connect(self):
        if not self.connected:
            self.ib = IB()
            await self.ib.connectAsync(
                    settings.IBKR_HOST, 
                    settings.IBKR_PORT, 
                    clientId=settings.IBKR_CLIENT_ID
                )
            self.connected = True
            logger.info("Connected to IBKR")

    def disconnect(self):
        if self.connected and self.ib is not None:
            self.ib.disconnect()
            self.connected = False
            logger.info("Disconnected from IBKR")

    async def setup_contract(self, symbol: str = settings.SYMBOL, exchange: str = settings.EXCHANGE, currency: str = settings.CURRENCY):
        if not self.connected:
             raise ConnectionError("Not connected to IBKR")

        # 1. Define the "Virtual" Continuous Contract (Equivalent to GC1!)
        # This is used for calculating signals or getting historical data
        self.continuous_contract = ContFuture(symbol=symbol, exchange=exchange, currency=currency)
        await self.ib.qualifyContractsAsync(self.continuous_contract)
        
        # 2. [NEW STEP] Find the "Real" Tradeable Contract
        # We look for the futures contract that matches the continuous contract's current month
        # Note: This logic finds the 'Front Month' which is what GC1! tracks.
        
        # Get the contract details to find the real expiration
        details = await self.ib.reqContractDetailsAsync(self.continuous_contract)
        
        if not details:
            raise ValueError("No liquid contract found for GC")

        # The first item in details for a ContFuture is usually the current front month
        self.tradeable_contract = details[0].contract
        
        logger.info(f"Data Contract (GC1!): {self.continuous_contract.localSymbol}")
        logger.info(f"Tradeable Contract:   {self.tradeable_contract.localSymbol}") # e.g., GCZ4

    async def req_historical_data(self):
        if not self.connected:
             raise ConnectionError("Not connected to IBKR")

        if not self.tradeable_contract:
            await self.setup_contract()
            
        # Request historical data with keepUpToDate=True to get real-time updates
        # This automatically updates the 'bars' list and fires updateEvent
        self.bars = await self.ib.reqHistoricalDataAsync(
            self.tradeable_contract,
            endDateTime='',
            durationStr='2 D',
            barSizeSetting='1 min',
            whatToShow='TRADES',
            useRTH=False,
            formatDate=1,
            keepUpToDate=True
        )
        self.df = util.df(self.bars)
        if self.df is None or self.df.empty:
            raise ValueError("Failed to load historical data")

        logger.info(f"Loaded {len(self.df)} historical bars and subscribed to updates")
        
        # Note: Trader will subscribe to self.bars.updateEvent
        # No need to hook here as it creates duplicate handlers

    def update_dataframe(self):
        """Update the dataframe from the current bars list"""
        if self.bars:
            self.df = util.df(self.bars)
            
    async def place_order(self, action: str, quantity: int, price: float = 0, order_type: str = 'MKT'):
        if not self.tradeable_contract:
            return None
            
        order = Order()
        order.action = action
        order.totalQuantity = quantity
        order.orderType = order_type
        if order_type in ['LMT', 'STOP', 'STP']:
            order.auxPrice = price # For STOP, auxPrice is the stop price
            
        trade = self.ib.placeOrder(self.tradeable_contract, order)
        return trade

    async def place_bracket_order(self, action: str, quantity: int, limit_price: float, stop_loss_price: float, take_profit_price: float):
        if not self.tradeable_contract:
            return None
            
        # Parent Order (Entry)
        parent = Order()
        parent.orderId = self.ib.client.getReqId()
        parent.action = action
        parent.totalQuantity = quantity
        parent.orderType = 'MKT' # Market Entry as per user request "This is a market order"
        # If limit_price is provided, maybe use LMT? User said "Market order".
        # But usually bracket starts with a parent.
        parent.transmit = False
        
        # Take Profit
        tp = Order()
        tp.orderId = self.ib.client.getReqId()
        tp.action = 'SELL' if action == 'BUY' else 'BUY'
        tp.totalQuantity = quantity
        tp.orderType = 'LMT'
        tp.lmtPrice = take_profit_price
        tp.parentId = parent.orderId
        tp.transmit = False
        
        # Stop Loss
        sl = Order()
        sl.orderId = self.ib.client.getReqId()
        sl.action = 'SELL' if action == 'BUY' else 'BUY'
        sl.totalQuantity = quantity
        sl.orderType = 'STP'
        sl.auxPrice = stop_loss_price
        sl.parentId = parent.orderId
        sl.transmit = True # Transmit the whole bracket
        
        trades = self.ib.placeOrder(self.tradeable_contract, parent)
        self.ib.placeOrder(self.tradeable_contract, tp)
        self.ib.placeOrder(self.tradeable_contract, sl)
        
        return trades

    async def get_positions(self):
        return self.ib.positions()

    async def get_pnl(self):
        """
        Get realized and unrealized PnL from IBKR.
        Returns a tuple of (realized_pnl, unrealized_pnl, total_pnl)
        """
        if not self.connected or self.ib is None:
            return 0.0, 0.0, 0.0
            
        # Request account summary - this gives us various account values
        account_summary = await self.ib.accountSummaryAsync()
        
        realized_pnl = 0.0
        unrealized_pnl = 0.0
        
        # Extract RealizedPnL and UnrealizedPnL from account summary
        for item in account_summary:
            if item.tag == 'RealizedPnL':
                realized_pnl = float(item.value)
            elif item.tag == 'UnrealizedPnL':
                unrealized_pnl = float(item.value)
        
        total_pnl = realized_pnl + unrealized_pnl
        return realized_pnl, unrealized_pnl, total_pnl
