import streamlit as st
import requests
import pandas as pd
import plotly.graph_objects as go
import time

API_URL = "http://localhost:8000"

st.set_page_config(page_title="IBKR Algo Dashboard", layout="wide")

st.title("LuxAlgo SMC Trading Bot")

# Sidebar Controls
st.sidebar.header("Controls")

if st.sidebar.button("Start Algo"):
    try:
        res = requests.post(f"{API_URL}/start")
        st.sidebar.success(res.json()["status"])
    except Exception as e:
        st.sidebar.error(f"Error: {e}")

if st.sidebar.button("Stop Algo"):
    try:
        res = requests.post(f"{API_URL}/stop")
        st.sidebar.warning(res.json()["status"])
    except Exception as e:
        st.sidebar.error(f"Error: {e}")

with st.sidebar.expander("Settings"):
    try:
        config = requests.get(f"{API_URL}/config").json()
        
        sl = st.number_input("Stop Loss (Ticks)", value=config.get("STOP_LOSS_TICKS", 20))
        tp = st.number_input("Take Profit (Ticks)", value=config.get("TAKE_PROFIT_TICKS", 20))
        lb = st.number_input("Lookback Bars", value=config.get("LOOKBACK_BARS", 5))
        
        if st.button("Update Settings"):
            res = requests.post(f"{API_URL}/config", json={
                "STOP_LOSS_TICKS": sl,
                "TAKE_PROFIT_TICKS": tp,
                "LOOKBACK_BARS": lb
            })
            if res.status_code == 200:
                st.success("Settings Updated")
            else:
                st.error("Failed to update")
    except Exception as e:
        st.error(f"Could not load settings: {e}")

# Status
try:
    status = requests.get(f"{API_URL}/status").json()
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Status", "Running" if status.get("running") else "Stopped")
    
    pnl_data = status.get('pnl', {})
    with col2:
        total_pnl = pnl_data.get('total', 0.0)
        st.metric("Total P&L", f"${total_pnl:.2f}", 
                 delta=f"${total_pnl:.2f}" if total_pnl != 0 else None,
                 delta_color="normal")
    with col3:
        realized_pnl = pnl_data.get('realized', 0.0)
        st.metric("Realized P&L", f"${realized_pnl:.2f}")
    with col4:
        unrealized_pnl = pnl_data.get('unrealized', 0.0)
        st.metric("Unrealized P&L", f"${unrealized_pnl:.2f}")
    
    st.metric("Positions", status.get("positions", 0))
except:
    st.error("Backend not reachable")

# Chart
st.header("Live Market Data (GC1!)")

try:
    data = requests.get(f"{API_URL}/data").json()
    if data["data"]:
        df = pd.DataFrame(data["data"])
        df['date'] = pd.to_datetime(df['date'])
        
        fig = go.Figure(data=[go.Candlestick(x=df['date'],
                        open=df['open'],
                        high=df['high'],
                        low=df['low'],
                        close=df['close'])])
        
        fig.update_layout(xaxis_rangeslider_visible=False, height=600)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No data available yet. Start the algo.")
except Exception as e:
    st.error(f"Error fetching data: {e}")

# Tabbed interface for Orders, Positions, and Trades
st.header("Trading Activity")

tab1, tab2, tab3 = st.tabs(["📋 All Orders", "💼 Open Positions", "📊 Trade History"])

with tab1:
    st.subheader("All Orders (Open & Filled)")
    try:
        orders_data = requests.get(f"{API_URL}/orders").json()
        if orders_data.get("connected"):
            orders = orders_data.get("orders", [])
            if orders:
                df_orders = pd.DataFrame(orders)
                # Format the dataframe for display
                display_cols = ["order_id", "symbol", "action", "total_quantity", 
                              "order_type", "status", "filled", "remaining", "avg_fill_price"]
                
                # Only include avg_fill_price if it exists in the data
                if "avg_fill_price" in df_orders.columns:
                    df_orders_display = df_orders[display_cols]
                else:
                    display_cols.remove("avg_fill_price")
                    df_orders_display = df_orders[display_cols]
                
                # Color code by status
                def highlight_status(row):
                    if row['status'] == 'Filled':
                        return ['background-color: #90EE90'] * len(row)
                    elif row['status'] in ['Submitted', 'PreSubmitted']:
                        return ['background-color: #FFFFE0'] * len(row)
                    elif row['status'] == 'Cancelled':
                        return ['background-color: #FFB6C1'] * len(row)
                    return [''] * len(row)
                
                st.dataframe(df_orders_display.style.apply(highlight_status, axis=1), 
                            use_container_width=True)
            else:
                st.info("✅ No orders found")
        else:
            st.warning("⚠️ Not connected to IBKR")
    except Exception as e:
        st.error(f"❌ Error fetching orders: {e}")

with tab2:
    st.subheader("Open Positions")
    try:
        positions_data = requests.get(f"{API_URL}/positions").json()
        if positions_data.get("connected"):
            positions = positions_data.get("positions", [])
            if positions:
                df_positions = pd.DataFrame(positions)
                
                # Format columns for better display
                if 'avg_cost' in df_positions.columns:
                    df_positions['avg_cost'] = df_positions['avg_cost'].apply(lambda x: f"${x:.2f}")
                
                st.dataframe(df_positions, use_container_width=True)
                
                # Summary metrics
                st.caption(f"Total positions: {len(df_positions)}")
            else:
                st.info("✅ No open positions")
        else:
            st.warning("⚠️ Not connected to IBKR")
    except Exception as e:
        st.error(f"❌ Error fetching positions: {e}")

with tab3:
    st.subheader("Trade History")
    
    # Filter options
    col1, col2, col3 = st.columns([1, 1, 3])
    with col1:
        trade_filter = st.selectbox("Status", ["All", "Open", "Closed"], index=0)
    with col2:
        limit = st.selectbox("Show", [10, 20, 50, 100], index=1)
    
    try:
        trades_data = requests.get(f"{API_URL}/trades").json()
        trades = trades_data.get("trades", [])
        
        st.caption(f"Total trades in database: {len(trades)}")
        
        if trades:
            df_trades = pd.DataFrame(trades)
            
            # Apply filter
            if trade_filter == "Open":
                df_trades = df_trades[df_trades['status'] == 'OPEN']
            elif trade_filter == "Closed":
                df_trades = df_trades[df_trades['status'] == 'CLOSED']
            
            if len(df_trades) == 0:
                st.info(f"✅ No {trade_filter.lower()} trades")
            else:
                # Format timestamps
                if 'entry_time' in df_trades.columns:
                    df_trades['entry_time'] = pd.to_datetime(df_trades['entry_time']).dt.strftime('%Y-%m-%d %H:%M')
                if 'exit_time' in df_trades.columns:
                    df_trades['exit_time'] = pd.to_datetime(df_trades['exit_time']).dt.strftime('%Y-%m-%d %H:%M')
                
                # Select columns for display
                display_cols = ['id', 'symbol', 'direction', 'quantity', 'entry_time', 
                               'entry_price', 'exit_price', 'status', 'pnl']
                df_trades_display = df_trades[display_cols].head(limit)
                
                # Color code PnL
                def color_pnl(val):
                    if pd.isna(val) or val == 0:
                        return ''
                    color = 'green' if val > 0 else 'red'
                    return f'color: {color}; font-weight: bold'
                
                styled_df = df_trades_display.style.applymap(color_pnl, subset=['pnl'])
                
                st.dataframe(styled_df, use_container_width=True)
                
                # Summary statistics
                if 'pnl' in df_trades.columns:
                    total_pnl = df_trades['pnl'].sum()
                    avg_pnl = df_trades['pnl'].mean()
                    
                    col1, col2, col3 = st.columns(3)
                    col1.metric("Trades Shown", len(df_trades_display))
                    col2.metric("Total PnL", f"${total_pnl:.2f}")
                    col3.metric("Avg PnL", f"${avg_pnl:.2f}")
        else:
            st.info("📊 No trades yet. Start the algo and wait for signals!")
            st.caption("Trades will appear here once the strategy detects CHoCH/BOS signals and executes orders.")
    except Exception as e:
        st.error(f"❌ Error fetching trades: {e}")
        st.caption("Check that the backend server is running and the database is accessible.")

# Auto-refresh
time.sleep(5)
st.rerun()
