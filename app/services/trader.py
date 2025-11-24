import asyncio
import logging
from datetime import datetime
from app.services.ib_connector import IBConnector
from app.services.smc_strategy import SMCStrategy, Trend, StructureType
from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.db.models import Trade, TradeStatus
from sqlalchemy import select, func

logger = logging.getLogger(__name__)

class Trader:
    def __init__(self):
        self.ib = IBConnector()
        self.strategy = SMCStrategy(
            swing_length=settings.LOOKBACK_BARS,
            internal_length=settings.INTERNAL_LENGTH,
            enable_confluence_filter=settings.ENABLE_CONFLUENCE_FILTER
        )
        self.running = False
        self.active_orders = {}
        self.current_pnl = 0.0
        # Track if we've already entered on current structure break
        self.last_entry_structure_index = None
        
    async def start(self):
        logger.info("=" * 60)
        logger.info("TRADER.START() CALLED")
        logger.info("=" * 60)
        
        self.running = True
        
        # Retry loop for connection
        while self.running:
            try:
                logger.info("Attempting to connect to IBKR...")
                await self.ib.connect()
                logger.info("✅ Connected to IBKR successfully")
                break
            except Exception as e:
                logger.error(f"Connection failed: {e}. Retrying in 5 seconds...")
                await asyncio.sleep(5)
        
        if not self.running:
            logger.warning("⚠️ Trader stopped before completing startup")
            return

        logger.info("🔍 Requesting historical data...")
        await self.ib.req_historical_data()
        logger.info(f"✅ Loaded {len(self.ib.df)} bars of historical data")
        
        # Subscribe to bar updates - CRITICAL: must be  after req_historical_data()
        logger.info(f"Subscribing to bar updates for {len(self.ib.bars)} bars")
        self.ib.bars.updateEvent += self.on_bar_update
        logger.info("✅ Event handler subscribed successfully")
        
        # Load initial PnL from DB
        await self.load_pnl()
        
        logger.info("Trader started and monitoring for bar updates")
        
        # Keep alive loop with periodic strategy checks
        # This ensures we check strategy even if bar update events aren't firing
        last_check = asyncio.get_event_loop().time()
        check_interval = 5.0  # Check strategy every 5 seconds as fallback
        
        while self.running:
            await asyncio.sleep(1)
            
            # Periodic fallback check (in case bar updates aren't firing)
            current_time = asyncio.get_event_loop().time()
            if current_time - last_check >= check_interval:
                logger.debug("⏱️ Periodic strategy check (fallback)")
                # Update dataframe from bars (in case IBKR updated silently)
                self.ib.update_dataframe()
                # Trigger strategy check
                asyncio.create_task(self.process_data())
                last_check = current_time
            
    async def stop(self):
        self.running = False
        self.ib.disconnect()
        logger.info("Trader stopped")

    async def load_pnl(self):
        """
        Load PnL from IBKR account if connected, otherwise from database.
        Uses IBKR realized PnL for position sizing decisions.
        """
        if self.ib.connected:
            try:
                # Get PnL from IBKR account
                realized_pnl, unrealized_pnl, total_pnl = await self.ib.get_pnl()
                self.current_pnl = realized_pnl  # Use realized PnL for position sizing
                logger.info(
                    f"PnL from IBKR - Realized: ${realized_pnl:.2f}, "
                    f"Unrealized: ${unrealized_pnl:.2f}, Total: ${total_pnl:.2f}"
                )
                return
            except Exception as e:
                logger.warning(f"Failed to get PnL from IBKR: {e}. Falling back to database.")
        
        # Fallback: Load from database
        try:
            async with AsyncSessionLocal() as session:
                # Sum realized PnL from closed trades
                result = await session.execute(
                    select(func.sum(Trade.pnl)).where(Trade.status == TradeStatus.CLOSED)
                )
                total_pnl = result.scalar() or 0.0
                self.current_pnl = total_pnl
                logger.info(f"Current Total PnL from DB: ${self.current_pnl:.2f}")
        except Exception as e:
            logger.error(f"Failed to load PnL from database: {e}")
            self.current_pnl = 0.0

    def calculate_position_size(self) -> int:
        """
        Position sizing based on PnL:
        - 1 contract initially
        - 2 contracts when profit > $3,000
        - 3 contracts when profit > $7,500
        """
        if self.current_pnl > 7500:
            return 3
        elif self.current_pnl > 3000:
            return 2
        else:
            return 1

    def on_bar_update(self, bars, hasNewBar):
        """Callback when new bar data arrives"""
        if not self.running:
            return
        
        # Update the dataframe in IBConnector
        self.ib.update_dataframe()
        
        # Log bar updates for debugging
        if hasNewBar:
            logger.info(f"📊 New bar received - Total bars: {len(self.ib.df)}")
        else:
            logger.debug(f"Bar update (tick) - Current price: {self.ib.df['close'].iloc[-1]:.2f}")
            
        asyncio.create_task(self.process_data())

    async def process_data(self):
        """
        Main trading logic:
        1. Update structure state with latest data
        2. Detect CHoCH/BOS breaks using internal structure
        3. Enter market orders when structure breaks
        4. Scale positions based on profit thresholds
        """
        df = self.ib.df
        
        # Need enough data
        if len(df) < max(self.strategy.swing_length, self.strategy.internal_length) + 1:
            logger.debug(f"Not enough data: {len(df)} bars")
            return

        logger.debug(f"🔍 Processing data - Bars: {len(df)}, Latest close: {df['close'].iloc[-1]:.2f}")

        # Check if we have active positions
        positions = await self.ib.get_positions()
        current_position_size = sum(abs(p.position) for p in positions)
        target_position_size = self.calculate_position_size()
        
        logger.debug(f"Current position size: {current_position_size}, Target: {target_position_size}")
        
        # ALWAYS update structure state and check for signals
        # Update structure state
        self.strategy.update_structure_state(df)
        
        # Detect structure breaks on the latest bar using INTERNAL structure
        structures = self.strategy.detect_structure_realtime(df, use_internal=True)
        
        if structures:
            logger.info(f"🎯 {len(structures)} structure(s) detected!")
        
        # Only enter new positions if:
        # 1. We have less than target position size (allows scaling)
        # 2. We haven't already processed this structure
        if current_position_size < target_position_size:
            if current_position_size == 0:
                logger.info("No active positions, looking for entries...")
            else:
                logger.info(f"Position scaling opportunity: {current_position_size} → {target_position_size}")
            
            # Process each structure break
            for struct in structures:
                # Prevent duplicate entries on same structure break
                if self.last_entry_structure_index == struct.index:
                    logger.info(f"Skipping duplicate entry on structure at index {struct.index}")
                    continue
                
                logger.info(
                    f"Structure Detected: {struct.type.value} {struct.trend.name} "
                    f"at price {struct.price:.2f}"
                )
                
                # Calculate quantity to add (difference between target and current)
                qty_to_add = target_position_size - current_position_size
                
                # Determine trade direction
                if struct.trend == Trend.BULLISH:
                    await self._enter_long(struct, qty_to_add)
                elif struct.trend == Trend.BEARISH:
                    await self._enter_short(struct, qty_to_add)
                
                # Mark this structure as processed
                self.last_entry_structure_index = struct.index
        elif current_position_size > 0:
            # We have a position at target size - just monitor (SL/TP are handled by broker)
            logger.debug(f"Position at target size ({current_position_size}), monitoring...")

    async def _enter_long(self, struct, quantity: int = None):
        """
        Enter LONG position on Bullish CHoCH or BOS.
        Entry is a MARKET order on the tick past the structure level.
        """
        qty = quantity if quantity is not None else self.calculate_position_size()
        current_price = self.ib.df['close'].iloc[-1]
        
        logger.info(
            f"🟢 LONG Entry Signal: {struct.type.value} @ {struct.price:.2f}, "
            f"Current: {current_price:.2f}, Qty: {qty}"
        )
        
        # Entry is market order (user requirement: "market order on tick past")
        await self.execute_trade("BUY", qty, current_price)

    async def _enter_short(self, struct, quantity: int = None):
        """
        Enter SHORT position on Bearish CHoCH or BOS.
        Entry is a MARKET order on the tick past the structure level.
        """
        qty = quantity if quantity is not None else self.calculate_position_size()
        current_price = self.ib.df['close'].iloc[-1]
        
        logger.info(
            f"🔴 SHORT Entry Signal: {struct.type.value} @ {struct.price:.2f}, "
            f"Current: {current_price:.2f}, Qty: {qty}"
        )
        
        # Entry is market order
        await self.execute_trade("SELL", qty, current_price)

    async def execute_trade(self, action: str, quantity: int, entry_price: float):
        """
        Execute trade with bracket order (Entry + SL + TP).
        
        Stop Loss: 2 points (20 ticks), NOT trailing, set in place
        Take Profit: 2 points (20 ticks)
        """
        # Calculate SL/TP
        # For GC (Gold), 1 point = 0.1 (typical tick size)
        # User wants 2 points = 2.0
        sl_dist = settings.STOP_LOSS_TICKS / 10.0  # 20 ticks = 2.0 points
        tp_dist = settings.TAKE_PROFIT_TICKS / 10.0  # 20 ticks = 2.0 points
        
        if action == "BUY":
            sl_price = entry_price - sl_dist
            tp_price = entry_price + tp_dist
        else:  # SELL
            sl_price = entry_price + sl_dist
            tp_price = entry_price - tp_dist
            
        logger.info(
            f"📊 Placing Bracket Order: {action} {quantity} @ ${entry_price:.2f} "
            f"| SL: ${sl_price:.2f} | TP: ${tp_price:.2f}"
        )
        
        # Place bracket order via IB
        try:
            await self.ib.place_bracket_order(action, quantity, entry_price, sl_price, tp_price)
            
            # Record trade in database
            async with AsyncSessionLocal() as session:
                trade = Trade(
                    symbol=settings.SYMBOL,
                    entry_price=entry_price,
                    quantity=quantity,
                    direction=action,
                    status=TradeStatus.OPEN,
                    stop_loss=sl_price,
                    take_profit=tp_price
                )
                session.add(trade)
                await session.commit()
                logger.info(f"✅ Trade recorded in database")
                
        except Exception as e:
            logger.error(f"❌ Error executing trade: {e}")

trader = Trader()
