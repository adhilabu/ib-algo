import streamlit as st
import requests
import pandas as pd
import plotly.graph_objects as go
import time

API_URL = "http://localhost:8005"

st.set_page_config(page_title="IBKR Algo Dashboard", layout="wide")

st.title("LuxAlgo SMC Trading Bot")

# Sidebar Controls (Static - no auto-refresh)
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

# Status and Metrics
try:
    status = requests.get(f"{API_URL}/status").json()
    account_data = requests.get(f"{API_URL}/account").json()
    account = account_data.get('account', {}) if account_data.get('connected') else {}
    
    # Display 6 key metrics in columns
    col1, col2, col3, col4, col5, col6 = st.columns(6)
    
    with col1:
        status_text = "🟢 Live" if status.get("running") else "⚪ Idle"
        st.metric("Status", status_text, label_visibility="collapsed")
    
    with col2:
        net_liq = account.get('NetLiquidation', 0.0)
        st.metric("💰 Net Value", f"${net_liq:,.0f}")
    
    with col3:
        buying_power = account.get('BuyingPower', 0.0)
        st.metric("⚡ Power", f"${buying_power:,.0f}")
    
    with col4:
        margin = account.get('MaintMarginReq', 0.0)
        st.metric("📊 Margin", f"${margin:,.0f}")
    
    pnl_data = status.get('pnl', {})
    with col5:
        total_pnl = pnl_data.get('total', 0.0)
        st.metric("💵 Total P&L", f"${total_pnl:.2f}", 
                 delta=f"${total_pnl:.2f}",
                 delta_color="normal")
    
    with col6:
        unrealized_pnl = pnl_data.get('unrealized', 0.0)
        st.metric("📈 Unreal.", f"${unrealized_pnl:.2f}",
                 delta=f"${unrealized_pnl:.2f}",
                 delta_color="normal")
except:
    st.error("Backend not reachable")

# Chart
st.header("Live Market Data (GC1!)")

try:
    data = requests.get(f"{API_URL}/data").json()
    
    # Debug info
    st.caption(f"Connected: {data.get('connected', False)} | Running: {data.get('running', False)} | Bars: {len(data.get('data', []))}")
    
    if data["data"]:
        df = pd.DataFrame(data["data"])
        df['date'] = pd.to_datetime(df['date'])
        
        fig = go.Figure(data=[go.Candlestick(x=df['date'],
                        open=df['open'],
                        high=df['high'],
                        low=df['low'],
                        close=df['close'])])
        
        fig.update_layout(xaxis_rangeslider_visible=False, height=600)
        st.plotly_chart(fig, width='stretch')
    else:
        st.info("No data available yet. Start the algo.")
except Exception as e:
    st.error(f"Error fetching data: {e}")
    import traceback
    st.code(traceback.format_exc())


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
                
                # Color code by status
                def highlight_status(row):
                    if row['status'] == 'Filled':
                        return ['background-color: #90EE90'] * len(row)
                    elif row['status'] in ['Submitted', 'PreSubmitted']:
                        return ['background-color: #FFFFE0'] * len(row)
                    elif row['status'] == 'Cancelled':
                        return ['background-color: #FFB6C1'] * len(row)
                    return [''] * len(row)
                
                # Format the dataframe for display
                display_cols = ["order_id", "symbol", "action", "total_quantity", 
                              "order_type", "status", "filled", "remaining"]
                if "avg_fill_price" in df_orders.columns:
                    display_cols.append("avg_fill_price")
                if "limit_price" in df_orders.columns:
                    display_cols.append("limit_price")
                
                df_orders_display = df_orders[display_cols]
                st.dataframe(df_orders_display.style.apply(highlight_status, axis=1), 
                            width='stretch')
                
                # Add action buttons for pending orders
                st.subheader("Order Actions")
                pending_orders = df_orders[df_orders['status'].isin(['Submitted', 'PreSubmitted'])]
                
                if len(pending_orders) > 0:
                    for idx, order in pending_orders.iterrows():
                        col1, col2, col3, col4 = st.columns([2, 1, 1, 1])
                        with col1:
                            st.write(f"Order #{order['order_id']}: {order['action']} {order['total_quantity']} {order['symbol']}")
                        with col2:
                            if order['order_type'] in ['LMT', 'STP', 'STP LMT']:
                                new_price = st.number_input(
                                    f"New price", 
                                    value=float(order.get('limit_price', 0) or 0),
                                    key=f"price_{order['order_id']}",
                                    step=0.01
                                )
                        with col3:
                            if st.button(f"✏️ Modify", key=f"mod_{order['order_id']}"):
                                if order['order_type'] in ['LMT', 'STP', 'STP LMT']:
                                    response = requests.post(
                                        f"{API_URL}/modify_order",
                                        params={"order_id": int(order['order_id']), "new_price": new_price}
                                    )
                                    if response.json().get('success'):
                                        st.success(f"Modified order {order['order_id']}")
                                        time.sleep(1)
                                        st.rerun()
                                    else:
                                        st.error(f"Failed: {response.json().get('error')}")
                        with col4:
                            if st.button(f"❌ Cancel", key=f"cancel_{order['order_id']}"):
                                response = requests.post(
                                    f"{API_URL}/cancel_order",
                                    params={"order_id": int(order['order_id'])}
                                )
                                if response.json().get('success'):
                                    st.success(f"Cancelled order {order['order_id']}")
                                    time.sleep(1)
                                    st.rerun()
                                else:
                                    st.error(f"Failed to cancel")
                else:
                    st.info("No pending orders to modify or cancel")
            else:
                st.info("✅ No orders found")
        else:
            st.warning("⚠️ Not connected to IBKR")
    except Exception as e:
        st.error(f"❌ Error fetching orders: {e}")

with tab2:
    st.subheader("Open Positions")
    try:
        portfolio_data = requests.get(f"{API_URL}/portfolio").json()
        if portfolio_data.get("connected"):
            portfolio = portfolio_data.get("portfolio", [])
            if portfolio:
                df_portfolio = pd.DataFrame(portfolio)
                
                # Calculate PnL percentage
                df_portfolio['pnl_pct'] = (df_portfolio['unrealized_pnl'] / 
                                          (df_portfolio['average_cost'] * abs(df_portfolio['position'])) * 100)
                
                # Display portfolio with formatting
                st.dataframe(
                    df_portfolio[['symbol', 'local_symbol', 'position', 'average_cost', 
                                 'market_price', 'market_value', 'unrealized_pnl', 'pnl_pct']]
                    .style.format({
                        'average_cost': '${:.2f}',
                        'market_price': '${:.2f}',
                        'market_value': '${:,.2f}',
                        'unrealized_pnl': '${:,.2f}',
                        'pnl_pct': '{:.2f}%'
                    })
                    .applymap(lambda x: 'color: green; font-weight: bold' if isinstance(x, (int, float)) and x > 0 
                             else ('color: red; font-weight: bold' if isinstance(x, (int, float)) and x < 0 else ''),
                             subset=['unrealized_pnl', 'pnl_pct']),
                    width='stretch'
                )
                
                # Action buttons for each position
                st.subheader("Position Actions")
                for idx, pos in df_portfolio.iterrows():
                    col1, col2, col3 = st.columns([3, 1, 1])
                    with col1:
                        direction = "LONG" if pos['position'] > 0 else "SHORT"
                        st.write(f"{pos['local_symbol']}: {direction} {abs(pos['position'])} @ ${pos['average_cost']:.2f} | "
                                f"P&L: ${pos['unrealized_pnl']:,.2f} ({pos['pnl_pct']:.2f}%)")
                    with col2:
                        if st.button(f"🔴 Close Position", key=f"close_{pos['local_symbol']}"):
                            response = requests.post(
                                f"{API_URL}/close_position",
                                params={
                                    "symbol": pos['symbol'],
                                    "local_symbol": pos['local_symbol'],
                                    "quantity": int(pos['position'])
                                }
                            )
                            if response.json().get('success'):
                                st.success(f"Closing {pos['local_symbol']}")
                                time.sleep(1)
                                st.rerun()
                            else:
                                st.error(f"Failed: {response.json().get('error')}")
                    with col3:
                        unrealized = pos['unrealized_pnl']
                        if unrealized > 0:
                            st.markdown("🟢 **Profit**")
                        elif unrealized < 0:
                            st.markdown("🔴 **Loss**")
                        else:
                            st.markdown("⚪ **Break-even**")
                
                # Summary metrics
                total_unrealized = df_portfolio['unrealized_pnl'].sum()
                total_value = df_portfolio['market_value'].sum()
                st.markdown("---")
                col1, col2 = st.columns(2)
                col1.metric("Total Market Value", f"${total_value:,.2f}")
                col2.metric("Total Unrealized P&L", f"${total_unrealized:,.2f}",
                           delta=f"${total_unrealized:,.2f}", delta_color="normal")
            else:
                st.info("✅ No open positions")
        else:
            st.warning("⚠️ Not connected to IBKR")
    except Exception as e:
        st.error(f"❌ Error fetching portfolio: {e}")
        import traceback
        st.code(traceback.format_exc())

with tab3:
    st.subheader("Trade History (Filled Orders)")
    
    # Filter options
    col1, col2 = st.columns([1, 3])
    with col1:
        limit = st.selectbox("Show", [10, 20, 50, 100], index=1)
    
    try:
        # Get all orders and filter for filled ones
        orders_data = requests.get(f"{API_URL}/orders").json()
        
        if orders_data.get("connected"):
            all_orders = orders_data.get("orders", [])
            
            # Filter for filled orders only
            filled_orders = [order for order in all_orders if order.get('status') == 'Filled']
            
            st.caption(f"Total filled orders: {len(filled_orders)}")
            
            if filled_orders:
                df_filled = pd.DataFrame(filled_orders)
                
                # Select and rename columns for display
                display_data = []
                for _, order in df_filled.iterrows():
                    display_data.append({
                        'Order ID': order['order_id'],
                        'Symbol': order['symbol'],
                        'Action': order['action'],
                        'Quantity': order['total_quantity'],
                        'Type': order['order_type'],
                        'Avg Price': f"${order.get('avg_fill_price', 0):.2f}" if order.get('avg_fill_price') else 'N/A',
                        'Status': order['status']
                    })
                
                df_display = pd.DataFrame(display_data).head(limit)
                
                # Apply color coding
                def color_action(val):
                    if val == 'BUY':
                        return 'color: green; font-weight: bold'
                    elif val == 'SELL':
                        return 'color: red; font-weight: bold'
                    return ''
                
                styled_df = df_display.style.applymap(color_action, subset=['Action'])
                st.dataframe(styled_df, width='stretch')
                
                # Summary statistics
                buy_orders = df_filled[df_filled['action'] == 'BUY']
                sell_orders = df_filled[df_filled['action'] == 'SELL']
                
                col1, col2, col3 = st.columns(3)
                col1.metric("Trades Shown", len(df_display))
                col2.metric("Buy Orders", len(buy_orders))
                col3.metric("Sell Orders", len(sell_orders))
            else:
                st.info("📊 No filled orders yet.")
                st.caption("Filled orders will appear here once trades are executed.")
        else:
            st.warning("⚠️ Not connected to IBKR")
    except Exception as e:
        st.error(f"❌ Error fetching trade history: {e}")
        import traceback
        st.code(traceback.format_exc())

# Auto-refresh every second for real-time chart updates
time.sleep(1)
st.rerun()
