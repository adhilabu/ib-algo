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

    async def get_account_summary(self):
        """
        Get comprehensive account summary including margin, buying power, etc.
        Returns a dictionary with key account metrics.
        """
        if not self.connected or self.ib is None:
            return {}
            
        account_summary = await self.ib.accountSummaryAsync()
        
        summary_dict = {}
        
        # Extract important account metrics
        for item in account_summary:
            # Convert value to float for numeric fields
            try:
                value = float(item.value)
            except (ValueError, TypeError):
                value = item.value
                
            summary_dict[item.tag] = value
        
        # Return commonly used fields with defaults
        return {
            'NetLiquidation': summary_dict.get('NetLiquidation', 0.0),
            'TotalCashValue': summary_dict.get('TotalCashValue', 0.0),
            'AvailableFunds': summary_dict.get('AvailableFunds', 0.0),
            'BuyingPower': summary_dict.get('BuyingPower', 0.0),
            'MaintMarginReq': summary_dict.get('MaintMarginReq', 0.0),
            'ExcessLiquidity': summary_dict.get('ExcessLiquidity', 0.0),
            'RealizedPnL': summary_dict.get('RealizedPnL', 0.0),
            'UnrealizedPnL': summary_dict.get('UnrealizedPnL', 0.0),
        }

    async def get_portfolio(self):
        """
        Get portfolio items with detailed position information and PnL.
        Returns a list of dictionaries with position details.
        """
        if not self.connected or self.ib is None:
            return []
            
        portfolio_items = self.ib.portfolio()
        
        portfolio_list = []
        for item in portfolio_items:
            portfolio_list.append({
                'symbol': item.contract.symbol if hasattr(item.contract, 'symbol') else 'N/A',
                'local_symbol': item.contract.localSymbol if hasattr(item.contract, 'localSymbol') else 'N/A',
                'position': item.position,
                'market_price': item.marketPrice,
                'market_value': item.marketValue,
                'average_cost': item.averageCost,
                'unrealized_pnl': item.unrealizedPNL,
                'realized_pnl': item.realizedPNL,
                'account': item.account,
            })
        
        return portfolio_list

    async def close_position(self, contract, quantity: int):
        """
        Close a position with a market order.
        Args:
            contract: The contract object or symbol
            quantity: The quantity to close (positive number)
        Returns:
            Trade object
        """
        if not self.connected or self.ib is None:
            logger.error("Not connected to IBKR")
            return None
            
        # Determine action based on current position
        # If quantity is positive in portfolio, we need to SELL to close
        # If quantity is negative (short), we need to BUY to close
        action = 'SELL' if quantity > 0 else 'BUY'
        
        order = MarketOrder(action, abs(quantity))
        trade = self.ib.placeOrder(contract, order)
        
        logger.info(f"Closing position: {action} {abs(quantity)} contracts")
        return trade

    async def cancel_order(self, order_id: int):
        """
        Cancel an order by order ID.
        Args:
            order_id: The order ID to cancel
        Returns:
            True if successful, False otherwise
        """
        if not self.connected or self.ib is None:
            logger.error("Not connected to IBKR")
            return False
            
        # Find the trade with this order ID
        trades = self.ib.trades()
        for trade in trades:
            if trade.order.orderId == order_id:
                self.ib.cancelOrder(trade.order)
                logger.info(f"Cancelled order {order_id}")
                return True
        
        logger.warning(f"Order {order_id} not found")
        return False

    async def modify_order(self, order_id: int, new_price: float):
        """
        Modify an existing order's price.
        Args:
            order_id: The order ID to modify
            new_price: The new limit/stop price
        Returns:
            True if successful, False otherwise
        """
        if not self.connected or self.ib is None:
            logger.error("Not connected to IBKR")
            return False
            
        # Find the trade with this order ID
        trades = self.ib.trades()
        for trade in trades:
            if trade.order.orderId == order_id:
                # Modify the order based on type
                if trade.order.orderType == 'LMT':
                    trade.order.lmtPrice = new_price
                elif trade.order.orderType in ['STP', 'STOP']:
                    trade.order.auxPrice = new_price
                elif trade.order.orderType == 'STP LMT':
                    trade.order.auxPrice = new_price
                
                # Re-place the order
                self.ib.placeOrder(trade.contract, trade.order)
                logger.info(f"Modified order {order_id} with new price {new_price}")
                return True
        
        logger.warning(f"Order {order_id} not found")
        return False
