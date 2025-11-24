from fastapi import FastAPI
from app.core.config import settings
import logging
import sys

# Configure logging to output to console
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

# Also enable DEBUG for our app modules
logging.getLogger('app').setLevel(logging.DEBUG)

app = FastAPI(title="IBKR Algo Trading - LuxAlgo SMC")

@app.get("/")
def read_root():
    return {"message": "IBKR Algo Trading System Operational", "status": "running"}

@app.get("/health")
def health_check():
    return {"status": "ok"}

from app.services.trader import trader
import asyncio
import logging

logger = logging.getLogger(__name__)

@app.post("/start")
async def start_trading():
    if not trader.running:
        async def start_with_error_handling():
            try:
                logger.info("🚀 Starting trader...")
                await trader.start()
            except Exception as e:
                logger.error(f"❌ Fatal error in trader.start(): {e}", exc_info=True)
                trader.running = False
        
        asyncio.create_task(start_with_error_handling())
        return {"status": "started"}
    return {"status": "already running"}

@app.post("/stop")
async def stop_trading():
    if trader.running:
        await trader.stop()
        return {"status": "stopped"}
    return {"status": "not running"}

@app.get("/status")
async def get_status():
    # Get real-time PnL if connected
    realized_pnl = 0.0
    unrealized_pnl = 0.0
    total_pnl = 0.0
    
    if trader.ib.connected and trader.ib.ib is not None:
        try:
            realized_pnl, unrealized_pnl, total_pnl = await trader.ib.get_pnl()
        except Exception as e:
            pass  # Fall back to trader.current_pnl
    
    return {
        "running": trader.running,
        "connected": trader.ib.connected,
        "pnl": {
            "realized": realized_pnl,
            "unrealized": unrealized_pnl,
            "total": total_pnl,
            "current": trader.current_pnl  # For position sizing
        },
        "positions": len(await trader.ib.get_positions()) if trader.ib.connected and trader.ib.ib is not None else 0
    }

@app.get("/data")
async def get_data():
    # Check if trader is connected and has data
    if not trader.ib.connected or not hasattr(trader.ib, 'df') or trader.ib.df is None or trader.ib.df.empty:
        return {"data": [], "connected": trader.ib.connected, "running": trader.running}
    
    # Return last 100 bars
    df = trader.ib.df.tail(100).copy()
    # Convert to dict
    return {"data": df.to_dict(orient="records"), "connected": True, "running": trader.running}

from pydantic import BaseModel

class ConfigUpdate(BaseModel):
    STOP_LOSS_TICKS: int
    TAKE_PROFIT_TICKS: int
    LOOKBACK_BARS: int

@app.get("/config")
def get_config():
    return {
        "STOP_LOSS_TICKS": settings.STOP_LOSS_TICKS,
        "TAKE_PROFIT_TICKS": settings.TAKE_PROFIT_TICKS,
        "LOOKBACK_BARS": settings.LOOKBACK_BARS
    }

@app.post("/config")
def update_config(config: ConfigUpdate):
    settings.STOP_LOSS_TICKS = config.STOP_LOSS_TICKS
    settings.TAKE_PROFIT_TICKS = config.TAKE_PROFIT_TICKS
    settings.LOOKBACK_BARS = config.LOOKBACK_BARS
    # Update strategy if needed
    trader.strategy.swing_length = settings.LOOKBACK_BARS
    return {"status": "updated", "config": config}

@app.get("/orders")
async def get_orders():
    """Get all orders (open and filled) from IBKR"""
    try:
        if not trader.ib.connected or trader.ib.ib is None:
            return {"orders": [], "connected": False}
        
        # Get all trades from IBKR (includes open and filled orders)
        trades = trader.ib.ib.trades()
        
        orders_data = []
        for trade in trades:
            # Extract contract symbol
            symbol = "N/A"
            if hasattr(trade.contract, 'symbol'):
                symbol = trade.contract.symbol
            elif hasattr(trade.contract, 'localSymbol'):
                symbol = trade.contract.localSymbol
            
            # Extract limit price if available
            limit_price = None
            if hasattr(trade.order, 'lmtPrice') and trade.order.lmtPrice:
                limit_price = trade.order.lmtPrice
            
            orders_data.append({
                "order_id": trade.order.orderId,
                "symbol": symbol,
                "action": trade.order.action,
                "total_quantity": trade.order.totalQuantity,
                "order_type": trade.order.orderType,
                "limit_price": limit_price,
                "status": trade.orderStatus.status,
                "filled": trade.orderStatus.filled,
                "remaining": trade.orderStatus.remaining,
                "avg_fill_price": trade.orderStatus.avgFillPrice if hasattr(trade.orderStatus, 'avgFillPrice') else None,
            })
        
        return {"orders": orders_data, "connected": True}
    except Exception as e:
        logger.error(f"Error fetching orders: {e}")
        return {"orders": [], "connected": False, "error": str(e)}

@app.get("/trades")
async def get_trades():
    """Get trade history from database"""
    try:
        from app.db.session import AsyncSessionLocal
        from app.db.models import Trade
        from sqlalchemy import select
        
        async with AsyncSessionLocal() as session:
            # Get last 50 trades, ordered by entry time descending
            result = await session.execute(
                select(Trade).order_by(Trade.entry_time.desc()).limit(50)
            )
            trades = result.scalars().all()
            
            trades_data = []
            for trade in trades:
                trades_data.append({
                    "id": trade.id,
                    "symbol": trade.symbol,
                    "entry_time": trade.entry_time.isoformat() if trade.entry_time else None,
                    "entry_price": trade.entry_price,
                    "exit_time": trade.exit_time.isoformat() if trade.exit_time else None,
                    "exit_price": trade.exit_price,
                    "quantity": trade.quantity,
                    "direction": trade.direction,
                    "status": trade.status,
                    "pnl": trade.pnl,
                    "stop_loss": trade.stop_loss,
                    "take_profit": trade.take_profit,
                })
            
            return {"trades": trades_data}
    except Exception as e:
        logger.error(f"Error fetching trades: {e}")
        return {"trades": [], "error": str(e)}

@app.get("/positions")
async def get_positions():
    """Get detailed position information from IBKR"""
    try:
        if not trader.ib.connected or trader.ib.ib is None:
            return {"positions": [], "connected": False}
        
        # Get all positions from IBKR
        positions = trader.ib.ib.positions()
        
        positions_data = []
        for pos in positions:
            # Only include positions with non-zero quantity
            if pos.position != 0:
                positions_data.append({
                    "symbol": pos.contract.symbol if hasattr(pos.contract, 'symbol') else "N/A",
                    "local_symbol": pos.contract.localSymbol if hasattr(pos.contract, 'localSymbol') else "N/A",
                    "position": pos.position,
                    "avg_cost": pos.avgCost,
                    "account": pos.account,
                })
        
        return {"positions": positions_data, "connected": True}
    except Exception as e:
        logger.error(f"Error fetching positions: {e}")
        return {"positions": [], "connected": False, "error": str(e)}


