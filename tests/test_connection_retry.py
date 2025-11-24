import asyncio
import logging
from unittest.mock import MagicMock, AsyncMock
from app.services.trader import Trader
from app.services.ib_connector import IBConnector

# Configure logging
logging.basicConfig(level=logging.INFO)

async def test_retry_logic():
    # Mock IBConnector
    trader = Trader()
    trader.ib = MagicMock(spec=IBConnector)
    trader.ib.connect = AsyncMock()
    trader.ib.bars = MagicMock()
    trader.ib.bars.updateEvent = MagicMock()
    
    # Simulate connection failure twice, then success
    trader.ib.connect.side_effect = [
        Exception("Connection refused"),
        Exception("Connection refused"),
        None
    ]
    
    # Mock req_historical_data to avoid actual calls
    trader.ib.req_historical_data = AsyncMock()
    
    # Mock load_pnl to avoid DB calls
    trader.load_pnl = AsyncMock()
    
    # Run start in a task so we can cancel it if it hangs
    task = asyncio.create_task(trader.start())
    
    # Wait for a bit to allow retries
    await asyncio.sleep(12)  # 2 retries * 5s + buffer
    
    # Stop trader
    trader.running = False
    await task
    
    # Verify call count
    assert trader.ib.connect.call_count == 3
    print("Test passed: Connection retried 3 times successfully.")

if __name__ == "__main__":
    asyncio.run(test_retry_logic())
