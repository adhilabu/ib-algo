# IB Algo Trading - LuxAlgo Smart Money Concepts

Algorithmic trading system for Interactive Brokers implementing the **LuxAlgo Smart Money Concepts** strategy on Gold Futures (GC1!) using 1-minute candles.

## 🎯 Strategy Overview

**Trading Logic**:
- **Entry**: Market order on CHoCH/BOS structure breaks using internal structure (5-bar lookback)
- **Stop Loss**: 2 points (20 ticks), not trailing
- **Take Profit**: 2 points (20 ticks)
- **Position Sizing**: 
  - 1 contract initially
  - 2 contracts when profit > $3,000
  - 3 contracts when profit > $7,500

**Smart Money Concepts**:
- Break of Structure (BOS) - trend continuation
- Change of Character (CHoCH) - trend reversal
- Internal structure (5-bar) for entries
- Swing structure (configurable) for context
- Order blocks and Fair Value Gaps detection
- Confluence filter for quality signals

## 🏗️ Architecture

```
ib-algo/
├── app/
│   ├── services/
│   │   ├── smc_strategy.py    # SMC strategy logic
│   │   ├── trader.py          # Trading execution
│   │   └── ib_connector.py    # IB connection
│   ├── db/
│   │   ├── models.py          # Database models
│   │   └── session.py         # DB session
│   ├── core/
│   │   └── config.py          # Configuration
│   └── main.py                # FastAPI server
├── ui/
│   └── dashboard.py           # Streamlit dashboard
├── verify_algo.py             # Test suite
├── deploy.sh                  # Deployment script
├── kill.sh                    # Shutdown script
└── docker-compose.yml         # PostgreSQL
```

## 📋 Prerequisites

- **Python**: 3.10+
- **Interactive Brokers**: TWS or IB Gateway
- **Docker**: For PostgreSQL
- **IB Account**: Paper or live trading account

## 🚀 Quick Start

### 1. Clone and Setup

```bash
# Navigate to project
cd /Users/adhilabubacker/Projects/ib-algo

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Environment

Create `.env` file:

```bash
# Database
POSTGRES_SERVER=localhost
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
POSTGRES_DB=ibalgo

# Interactive Brokers
IBKR_HOST=127.0.0.1
IBKR_PORT=7497              # 7497 for TWS Paper, 4001 for Gateway Paper
IBKR_CLIENT_ID=1

# Trading
SYMBOL=GC!
EXCHANGE=COMEX
CURRENCY=USD
TIMEFRAME=1 min

# Strategy Parameters
STOP_LOSS_TICKS=20          # 2 points
TAKE_PROFIT_TICKS=20        # 2 points
LOOKBACK_BARS=5             # Swing structure
INTERNAL_LENGTH=5           # Internal structure (entries)
ENABLE_CONFLUENCE_FILTER=True
FVG_THRESHOLD_ENABLED=True
```

### 3. Start Interactive Brokers

**TWS (Trader Workstation)**:
1. Launch TWS
2. Login to Paper Trading account
3. Configure → Settings → API → Settings
4. Enable "Enable ActiveX and Socket Clients"
5. Socket port: 7497
6. Trusted IPs: 127.0.0.1

**IB Gateway** (headless):
1. Launch IB Gateway
2. Login to Paper Trading
3. Socket port: 4001

### 4. Deploy

```bash
# Make scripts executable
chmod +x deploy.sh kill.sh

# Deploy everything
./deploy.sh
```

This will:
- Start PostgreSQL container
- Run database migrations
- Start FastAPI backend
- Start Streamlit dashboard (optional)

### 5. Start Trading

**Via API**:
```bash
# Start trading
curl -X POST http://localhost:8000/start

# Check status
curl http://localhost:8000/status

# View configuration
curl http://localhost:8000/config

# Stop trading
curl -X POST http://localhost:8000/stop
```

**Via Dashboard**:
- Open browser: http://localhost:8501
- Click "Start Trading"

## 🧪 Testing

### Run Verification Tests

```bash
source venv/bin/activate
python verify_algo.py
```

**Tests Include**:
- ✅ Pivot detection (swing + internal)
- ✅ CHoCH/BOS structure detection
- ✅ Real-time structure tracking
- ✅ Confluence filter
- ✅ Order block detection
- ✅ Fair Value Gap detection
- ✅ State machine validation

### Expected Output

```
✓ Swing Pivots (10-bar): 71 Highs, 65 Lows
✓ Internal Pivots (5-bar): 81 Highs, 73 Lows
✓ Total Structures Detected: 6
  - CHoCH: 5
  - BOS: 1
✓ Order Blocks Detected: 6
✓ Fair Value Gaps Detected: 13
```

## 📊 API Endpoints

### Trading Control

```bash
POST /start              # Start trading
POST /stop               # Stop trading
GET  /status             # Get trading status
```

### Configuration

```bash
GET  /config             # Get current config
POST /config             # Update config
```

### Data

```bash
GET  /data               # Get latest price data
GET  /trades             # Get trade history
GET  /positions          # Get open positions
```

## 🎛️ Configuration

Edit `app/core/config.py` or use API:

```python
# Strategy Parameters
STOP_LOSS_TICKS = 20        # 2 points
TAKE_PROFIT_TICKS = 20      # 2 points
LOOKBACK_BARS = 5           # Swing structure lookback
INTERNAL_LENGTH = 5         # Internal structure (for entries)
ENABLE_CONFLUENCE_FILTER = True
FVG_THRESHOLD_ENABLED = True

# Position Sizing
# Automatically scales: 1 → 2 → 3 contracts based on PnL
```

**Update via API**:
```bash
curl -X POST http://localhost:8000/config \
  -H "Content-Type: application/json" \
  -d '{
    "STOP_LOSS_TICKS": 20,
    "TAKE_PROFIT_TICKS": 20,
    "LOOKBACK_BARS": 5
  }'
```

## 📝 Monitoring

### Logs

```bash
# Backend logs
tail -f logs/trading.log

# View structure detection
grep "Structure Detected" logs/trading.log

# View trades
grep "Placing Bracket Order" logs/trading.log
```

### Database Queries

```bash
# Connect to PostgreSQL
docker exec -it ib-algo-postgres psql -U postgres -d ibalgo

# View trades
SELECT * FROM trades ORDER BY created_at DESC LIMIT 10;

# Check PnL
SELECT SUM(pnl) FROM trades WHERE status = 'CLOSED';
```

## 🛑 Shutdown

```bash
./kill.sh
```

This will:
- Stop the trading bot
- Stop FastAPI server
- Stop Streamlit dashboard
- Stop PostgreSQL container

## 🐛 Troubleshooting

### Connection Issues

**"IB connection failed"**:
- Check TWS/Gateway is running
- Verify port (7497 for TWS, 4001 for Gateway)
- Check API settings in TWS
- Ensure "Enable ActiveX and Socket Clients" is checked

**"Database connection error"**:
```bash
# Restart PostgreSQL
docker-compose down
docker-compose up -d
```

### Trading Issues

**"No structures detected"**:
- Need 50+ bars of data
- Check logs: `tail -f logs/trading.log`
- Run tests: `python verify_algo.py`

**"Duplicate entries"**:
- Check `last_entry_structure_index` in logs
- Should be prevented automatically

**"Wrong entry level"**:
- Verify using internal structure (5-bar)
- Compare with TradingView LuxAlgo indicator
- Check confluence filter status

### Data Issues

**"Not enough data"**:
- Wait for IB to load historical data
- Check IBKR data subscriptions for GC
- Verify market hours

## 📚 Strategy Validation

### Compare with TradingView

1. Open TradingView
2. Add LuxAlgo Smart Money Concepts indicator
3. Settings:
   - Enable "Internal Structure"
   - Lookback: 5
   - Enable confluence filter
4. Compare CHoCH/BOS markers with your logs

### Paper Trading Checklist

- [ ] Paper traded for 1-2 days
- [ ] Verified structures match TradingView
- [ ] Confirmed entries only on CHoCH/BOS
- [ ] Validated SL/TP distances (2 points)
- [ ] Tested position sizing (1→2→3)
- [ ] Reviewed all trades in database
- [ ] No duplicate entries observed

## 🔐 Security

**Never commit**:
- `.env` file (contains credentials)
- API keys
- Account numbers

**Production Recommendations**:
- Use environment variables
- Implement rate limiting
- Add authentication to API
- Use HTTPS
- Monitor for anomalies

## 📄 License

This project is for personal use. The LuxAlgo Smart Money Concepts indicator is licensed under CC BY-NC-SA 4.0.

## 🤝 Support

For issues:
1. Check logs: `tail -f logs/trading.log`
2. Run tests: `python verify_algo.py`
3. Verify IB connection
4. Check database connectivity

## 📈 Performance Tracking

Monitor via:
- Streamlit dashboard: http://localhost:8501
- API status: http://localhost:8000/status
- Database queries
- Log files

---

**⚠️ Risk Warning**: Trading involves substantial risk. This system is provided as-is. Always test thoroughly in paper trading before going live.
