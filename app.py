"""
Portfolio P&L Tracker - Streamlit Cloud Version
Tracks scrip-wise profit/loss with LTCG/STCG bifurcation.
No Snowflake dependency - uses CSV files and yfinance for live prices.
"""

import streamlit as st
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
from collections import defaultdict
import os

# ============================================================
# CONFIGURATION
# ============================================================

# Paths relative to this file (works on Streamlit Cloud)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(BASE_DIR, "data", "portfolio.csv")
PRICES_CSV_PATH = os.path.join(BASE_DIR, "data", "latest_prices.csv")

# Ticker mapping: Portfolio CSV symbol -> Yahoo Finance ticker
TICKER_MAP = {
    "ARTMED": "ARTEMISMED.NS",
    "ATHENE": "ATHERENERG.NS",
    "BAJFI": "BAJFINANCE.NS",
    "BHAINF": "INDUSTOWER.NS",
    "BSE": "BSE.NS",
    "CANROB": "CRAMC.NS",
    "CENTEX": "ABREL.NS",
    "DIXTEC": "DIXON.NS",
    "EICMOT": "EICHERMOT.NS",
    "GODPRO": "GODREJPROP.NS",
    "HINZIN": "HINDZINC.NS",
    "ICIBAN": "ICICIBANK.NS",
    "INDEN": "IEX.NS",
    "INDHOT": "INDHOTEL.NS",
    "INVGOL": "IVZINGOLD.NS",
    "LARTOU": "LT.NS",
    "LTINFO": "LTM.NS",
    "MARUTI": "MARUTI.NS",
    "MOTNAS": "MON100.NS",
    "NIFJUN": "JUNIORBEES.NS",
    "NIITEC": "COFORGE.NS",
    "PERSYS": "PERSISTENT.NS",
    "RADKHA": "RADICO.NS",
    "RELNIP": "NAM-INDIA.NS",
    "SHRPRO": "SHRIRAMPPS.NS",
    "TATMOT": "TMPV.NS",
    "TATPOW": "TATAPOWER.NS",
    "TATSIL": "TATSILV.NS",
    "VEDLIM": "VEDL.NS",
    "YESBAN": "YESBANK.NS",
}


# ============================================================
# DATA LOADING
# ============================================================

@st.cache_data
def load_data():
    """Load and parse the portfolio CSV."""
    df = pd.read_csv(CSV_PATH)
    df = df.loc[:, ~df.columns.str.contains('^Unnamed')]
    df.columns = df.columns.str.strip()
    df['Transaction Date'] = pd.to_datetime(df['Transaction Date'], format='%d-%b-%Y')
    for col in ['Quantity', 'Transaction Price', 'Brokerage', 'Transaction Charges', 'StampDuty']:
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
    df = df.sort_values(['Stock Symbol', 'Transaction Date']).reset_index(drop=True)
    return df


# ============================================================
# FIFO MATCHING LOGIC
# ============================================================

def calculate_fifo(df):
    """Apply FIFO matching for realized P&L with LTCG/STCG classification."""
    realized_trades = []
    holdings = defaultdict(list)

    for symbol in df['Stock Symbol'].unique():
        sym_df = df[df['Stock Symbol'] == symbol].sort_values(['Transaction Date', 'Action'])
        buy_queue = []

        for date, day_group in sym_df.groupby('Transaction Date', sort=True):
            day_buys = day_group[day_group['Action'] == 'Buy']
            day_sells = day_group[day_group['Action'] == 'Sell']

            same_day_lots = []
            for _, row in day_buys.iterrows():
                qty = int(row['Quantity'])
                price = float(row['Transaction Price'])
                brokerage = float(row['Brokerage'])
                charges = float(row['Transaction Charges']) + float(row['StampDuty'])
                company = row['Company Name']
                total_cost = (price * qty) + brokerage + charges
                cost_per_unit = total_cost / qty if qty > 0 else 0
                same_day_lots.append({
                    'date': date, 'qty': qty, 'price': price,
                    'cost_per_unit': cost_per_unit, 'company': company,
                })

            for _, row in day_sells.iterrows():
                qty = int(row['Quantity'])
                price = float(row['Transaction Price'])
                brokerage = float(row['Brokerage'])
                charges = float(row['Transaction Charges']) + float(row['StampDuty'])
                company = row['Company Name']
                sell_qty_remaining = qty
                total_sale = (price * qty) - brokerage - charges
                sale_per_unit = total_sale / qty if qty > 0 else 0

                # Match against same-day buys first
                while sell_qty_remaining > 0 and same_day_lots:
                    lot = same_day_lots[0]
                    matched_qty = min(sell_qty_remaining, lot['qty'])
                    pnl = (sale_per_unit - lot['cost_per_unit']) * matched_qty
                    realized_trades.append({
                        'Symbol': symbol, 'Company': company,
                        'Buy Date': lot['date'], 'Buy Price': lot['price'],
                        'Buy Cost/Unit': lot['cost_per_unit'],
                        'Sell Date': date, 'Sell Price': price,
                        'Sale/Unit': sale_per_unit, 'Qty': matched_qty,
                        'Holding Days': 0, 'Gain Type': 'STCG', 'P&L': pnl,
                    })
                    lot['qty'] -= matched_qty
                    sell_qty_remaining -= matched_qty
                    if lot['qty'] == 0:
                        same_day_lots.pop(0)

                # Then match against older lots (standard FIFO)
                while sell_qty_remaining > 0 and buy_queue:
                    lot = buy_queue[0]
                    matched_qty = min(sell_qty_remaining, lot['qty'])
                    holding_days = (date - lot['date']).days
                    gain_type = "LTCG" if holding_days > 365 else "STCG"
                    pnl = (sale_per_unit - lot['cost_per_unit']) * matched_qty
                    realized_trades.append({
                        'Symbol': symbol, 'Company': company,
                        'Buy Date': lot['date'], 'Buy Price': lot['price'],
                        'Buy Cost/Unit': lot['cost_per_unit'],
                        'Sell Date': date, 'Sell Price': price,
                        'Sale/Unit': sale_per_unit, 'Qty': matched_qty,
                        'Holding Days': holding_days, 'Gain Type': gain_type, 'P&L': pnl,
                    })
                    lot['qty'] -= matched_qty
                    sell_qty_remaining -= matched_qty
                    if lot['qty'] == 0:
                        buy_queue.pop(0)

            for lot in same_day_lots:
                if lot['qty'] > 0:
                    buy_queue.append(lot)

        if buy_queue:
            holdings[symbol] = buy_queue

    return realized_trades, dict(holdings)


# ============================================================
# PRICE FETCHING (yfinance only, no Snowflake)
# ============================================================

@st.cache_data(ttl=300)
def fetch_current_prices(symbols):
    """Fetch current market prices from yfinance."""
    prices = {}
    for sym in symbols:
        yf_ticker = TICKER_MAP.get(sym)
        if not yf_ticker:
            continue
        try:
            ticker = yf.Ticker(yf_ticker)
            hist = ticker.history(period="5d")
            if not hist.empty:
                valid = hist[hist['Close'].notna()]
                if not valid.empty:
                    prices[sym] = valid['Close'].iloc[-1]
        except:
            pass
    return prices


def fetch_prev_close_prices(symbols):
    """Fetch previous trading day close from latest_prices.csv (PREV_CLOSE column)."""
    if not os.path.exists(PRICES_CSV_PATH):
        return {}, {}
    try:
        prices_df = pd.read_csv(PRICES_CSV_PATH)

        # Build symbol mapping: portfolio symbol -> price-table symbol
        price_symbols = {}
        for sym in symbols:
            yf_ticker = TICKER_MAP.get(sym)
            if yf_ticker:
                price_sym = yf_ticker.replace('.NS', '').replace('.BO', '').replace('-', '_')
                price_symbols[sym] = price_sym

        # Use PREV_CLOSE if available
        if 'PREV_CLOSE' in prices_df.columns:
            csv_prices = dict(zip(prices_df['SYMBOL'], prices_df['PREV_CLOSE']))
        else:
            csv_prices = dict(zip(prices_df['SYMBOL'], prices_df['CLOSE_PRICE']))

        # Get prev close date
        if 'PREV_DATE' in prices_df.columns:
            csv_dates = dict(zip(prices_df['SYMBOL'], prices_df['PREV_DATE']))
        elif 'TRADE_DATE' in prices_df.columns:
            csv_dates = dict(zip(prices_df['SYMBOL'], prices_df['TRADE_DATE']))
        else:
            csv_dates = {}

        prices = {}
        dates = {}
        for sym, price_sym in price_symbols.items():
            if price_sym in csv_prices and pd.notna(csv_prices.get(price_sym)):
                prices[sym] = float(csv_prices[price_sym])
                dates[sym] = csv_dates.get(price_sym, '')
        return prices, dates
    except Exception:
        return {}, {}


@st.cache_data(ttl=60)
def fetch_live_prices(symbols):
    """Fetch live prices via yfinance (for Today's P&L tab)."""
    return fetch_current_prices(symbols)


# ============================================================
# STREAMLIT APP
# ============================================================

st.set_page_config(page_title="Portfolio P&L Tracker", page_icon="📊", layout="wide")
st.title("📊 Portfolio P&L Tracker")
st.caption("FIFO-based Profit & Loss with LTCG/STCG bifurcation")

# Load data
df = load_data()
realized_trades, holdings = calculate_fifo(df)
realized_df = pd.DataFrame(realized_trades)

# Sidebar navigation
page = st.sidebar.radio("Navigate", ["Realized P&L", "Current Holdings", "Today's P&L", "Portfolio Summary"])


# ============================================================
# PAGE 1: REALIZED P&L
# ============================================================

if page == "Realized P&L":
    st.header("Scrip-wise Realized Profit & Loss")

    if realized_df.empty:
        st.info("No realized trades found.")
    else:
        summary = realized_df.groupby(['Symbol', 'Company']).agg(
            Total_Trades=('Qty', 'count'),
            Total_Qty_Sold=('Qty', 'sum'),
            STCG=('P&L', lambda x: x[realized_df.loc[x.index, 'Gain Type'] == 'STCG'].sum()),
            LTCG=('P&L', lambda x: x[realized_df.loc[x.index, 'Gain Type'] == 'LTCG'].sum()),
            Net_PnL=('P&L', 'sum'),
        ).reset_index()

        st.subheader("Summary")
        col1, col2, col3 = st.columns(3)
        total_pnl = summary['Net_PnL'].sum()
        total_stcg = summary['STCG'].sum()
        total_ltcg = summary['LTCG'].sum()
        col1.metric("Total Realized P&L", f"₹{total_pnl:,.2f}", delta=f"{'Profit' if total_pnl >= 0 else 'Loss'}")
        col2.metric("Short Term Gains (STCG)", f"₹{total_stcg:,.2f}")
        col3.metric("Long Term Gains (LTCG)", f"₹{total_ltcg:,.2f}")

        st.divider()
        display_summary = summary[['Symbol', 'Company', 'Total_Qty_Sold', 'STCG', 'LTCG', 'Net_PnL']].copy()
        display_summary.columns = ['Symbol', 'Company', 'Qty Sold', 'STCG (₹)', 'LTCG (₹)', 'Net P&L (₹)']
        display_summary = display_summary.sort_values('Net P&L (₹)', ascending=False)
        st.dataframe(
            display_summary.style.format({
                'STCG (₹)': '₹{:,.2f}', 'LTCG (₹)': '₹{:,.2f}', 'Net P&L (₹)': '₹{:,.2f}',
            }).map(
                lambda x: 'color: green' if isinstance(x, (int, float)) and x > 0 else 'color: red' if isinstance(x, (int, float)) and x < 0 else '',
                subset=['STCG (₹)', 'LTCG (₹)', 'Net P&L (₹)']
            ),
            use_container_width=True, hide_index=True,
        )

        st.divider()
        st.subheader("Trade-level Details")
        selected_scrip = st.selectbox(
            "Select Scrip", options=sorted(realized_df['Symbol'].unique()),
            format_func=lambda x: f"{x} - {realized_df[realized_df['Symbol']==x]['Company'].iloc[0]}"
        )
        if selected_scrip:
            scrip_trades = realized_df[realized_df['Symbol'] == selected_scrip].copy()
            scrip_trades['Buy Date'] = scrip_trades['Buy Date'].dt.strftime('%d-%b-%Y')
            scrip_trades['Sell Date'] = scrip_trades['Sell Date'].dt.strftime('%d-%b-%Y')
            display_trades = scrip_trades[['Buy Date', 'Buy Price', 'Sell Date', 'Sell Price', 'Qty', 'Holding Days', 'Gain Type', 'P&L']].copy()
            display_trades.columns = ['Buy Date', 'Buy Price', 'Sell Date', 'Sell Price', 'Qty', 'Days Held', 'Type', 'P&L (₹)']
            st.dataframe(
                display_trades.style.format({'Buy Price': '₹{:,.2f}', 'Sell Price': '₹{:,.2f}', 'P&L (₹)': '₹{:,.2f}'}).map(
                    lambda x: 'color: green' if isinstance(x, (int, float)) and x > 0 else 'color: red' if isinstance(x, (int, float)) and x < 0 else '',
                    subset=['P&L (₹)']
                ),
                use_container_width=True, hide_index=True,
            )


# ============================================================
# PAGE 2: CURRENT HOLDINGS
# ============================================================

elif page == "Current Holdings":
    st.header("Current Holdings & Unrealized P&L")

    if not holdings:
        st.info("No current holdings found.")
    else:
        with st.spinner("Fetching current market prices..."):
            current_prices = fetch_current_prices(list(holdings.keys()))

        holdings_data = []
        today = datetime.now()

        for symbol, lots in holdings.items():
            total_qty = sum(lot['qty'] for lot in lots)
            if total_qty == 0:
                continue
            total_cost = sum(lot['qty'] * lot['cost_per_unit'] for lot in lots)
            avg_cost = total_cost / total_qty if total_qty > 0 else 0
            company = lots[0]['company']
            current_price = current_prices.get(symbol, 0)
            current_value = current_price * total_qty
            unrealized_pnl = current_value - total_cost
            pnl_pct = ((current_price - avg_cost) / avg_cost * 100) if avg_cost > 0 else 0

            ltcg_unrealized = 0
            stcg_unrealized = 0
            for lot in lots:
                holding_days = (today - lot['date']).days
                lot_pnl = (current_price - lot['cost_per_unit']) * lot['qty']
                if holding_days > 365:
                    ltcg_unrealized += lot_pnl
                else:
                    stcg_unrealized += lot_pnl

            holdings_data.append({
                'Symbol': symbol, 'Company': company, 'Qty': total_qty,
                'Avg Cost': avg_cost, 'Current Price': current_price,
                'Invested': total_cost, 'Current Value': current_value,
                'Unrealized P&L': unrealized_pnl, 'P&L %': pnl_pct,
                'STCG (Unrealized)': stcg_unrealized, 'LTCG (Unrealized)': ltcg_unrealized,
            })

        holdings_df = pd.DataFrame(holdings_data)

        if holdings_df.empty:
            st.info("No current holdings with price data.")
        else:
            col1, col2, col3, col4 = st.columns(4)
            total_invested = holdings_df['Invested'].sum()
            total_current = holdings_df['Current Value'].sum()
            total_unrealized = holdings_df['Unrealized P&L'].sum()
            total_pct = ((total_current - total_invested) / total_invested * 100) if total_invested > 0 else 0
            col1.metric("Total Invested", f"₹{total_invested:,.0f}")
            col2.metric("Current Value", f"₹{total_current:,.0f}")
            col3.metric("Unrealized P&L", f"₹{total_unrealized:,.0f}", delta=f"{total_pct:+.1f}%")
            col4.metric("# Stocks", f"{len(holdings_df)}")

            st.divider()
            total_stcg_u = holdings_df['STCG (Unrealized)'].sum()
            total_ltcg_u = holdings_df['LTCG (Unrealized)'].sum()
            col1, col2 = st.columns(2)
            col1.metric("Unrealized STCG", f"₹{total_stcg_u:,.0f}")
            col2.metric("Unrealized LTCG", f"₹{total_ltcg_u:,.0f}")

            st.divider()
            display_holdings = holdings_df[['Symbol', 'Company', 'Qty', 'Avg Cost', 'Current Price',
                                            'Invested', 'Current Value', 'Unrealized P&L', 'P&L %',
                                            'STCG (Unrealized)', 'LTCG (Unrealized)']].copy()
            display_holdings = display_holdings.sort_values('Unrealized P&L', ascending=False)
            st.dataframe(
                display_holdings.style.format({
                    'Avg Cost': '₹{:,.2f}', 'Current Price': '₹{:,.2f}',
                    'Invested': '₹{:,.0f}', 'Current Value': '₹{:,.0f}',
                    'Unrealized P&L': '₹{:,.0f}', 'P&L %': '{:+.1f}%',
                    'STCG (Unrealized)': '₹{:,.0f}', 'LTCG (Unrealized)': '₹{:,.0f}',
                }).map(
                    lambda x: 'color: green' if isinstance(x, (int, float)) and x > 0 else 'color: red' if isinstance(x, (int, float)) and x < 0 else '',
                    subset=['Unrealized P&L', 'P&L %', 'STCG (Unrealized)', 'LTCG (Unrealized)']
                ),
                use_container_width=True, hide_index=True,
            )


# ============================================================
# PAGE 3: TODAY'S P&L (Live vs Previous Close)
# ============================================================

elif page == "Today's P&L":
    st.header("Today's P&L - Live Market View")

    if not holdings:
        st.info("No current holdings found.")
    else:
        holding_symbols = list(holdings.keys())

        with st.spinner("Fetching previous close prices..."):
            prev_close, prev_dates = fetch_prev_close_prices(holding_symbols)

        with st.spinner("Fetching live/current prices..."):
            live_prices = fetch_live_prices(holding_symbols)
            ltp_time = datetime.now().strftime('%d-%b-%Y %H:%M')

        todays_data = []
        for symbol, lots in holdings.items():
            total_qty = sum(lot['qty'] for lot in lots)
            if total_qty == 0:
                continue
            company = lots[0]['company']
            prev = prev_close.get(symbol)
            ltp = live_prices.get(symbol)
            if prev is None or ltp is None:
                continue
            change_rs = ltp - prev
            change_pct = (change_rs / prev * 100) if prev > 0 else 0
            day_pnl = change_rs * total_qty
            todays_data.append({
                'Symbol': symbol, 'Company': company, 'Qty': total_qty,
                'Prev Close': prev, 'Prev Close Date': prev_dates.get(symbol, ''),
                'LTP': ltp, 'LTP Time': ltp_time,
                'Change (Rs)': change_rs, 'Change (%)': change_pct,
                'Day P&L (Rs)': day_pnl,
            })

        if not todays_data:
            st.warning("Unable to fetch prices. Ensure data/latest_prices.csv has PREV_CLOSE column.")
        else:
            todays_df = pd.DataFrame(todays_data)
            total_day_pnl = todays_df['Day P&L (Rs)'].sum()
            gainers_count = len(todays_df[todays_df['Change (Rs)'] > 0])
            losers_count = len(todays_df[todays_df['Change (Rs)'] < 0])
            unchanged_count = len(todays_df[todays_df['Change (Rs)'] == 0])

            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Today's Portfolio P&L", f"₹{total_day_pnl:,.0f}",
                        delta=f"{'Profit' if total_day_pnl >= 0 else 'Loss'}")
            col2.metric("Gainers", f"{gainers_count}", delta="up", delta_color="normal")
            col3.metric("Losers", f"{losers_count}", delta="down", delta_color="inverse")
            col4.metric("Unchanged", f"{unchanged_count}")

            st.divider()
            display_today = todays_df.sort_values('Day P&L (Rs)', ascending=False)
            st.dataframe(
                display_today.style.format({
                    'Prev Close': '₹{:,.2f}', 'LTP': '₹{:,.2f}',
                    'Change (Rs)': '{:+,.2f}', 'Change (%)': '{:+.2f}%',
                    'Day P&L (Rs)': '₹{:+,.0f}',
                }).map(
                    lambda x: 'color: green' if isinstance(x, (int, float)) and x > 0 else 'color: red' if isinstance(x, (int, float)) and x < 0 else '',
                    subset=['Change (Rs)', 'Change (%)', 'Day P&L (Rs)']
                ),
                use_container_width=True, hide_index=True,
            )

            st.divider()
            col1, col2 = st.columns(2)
            with col1:
                st.subheader("Top Gainers Today")
                top_gain = display_today[display_today['Day P&L (Rs)'] > 0].head(5)
                for _, row in top_gain.iterrows():
                    st.write(f"**{row['Symbol']}** ({row['Company']}): ₹{row['Day P&L (Rs)']:+,.0f} ({row['Change (%)']:+.2f}%)")
            with col2:
                st.subheader("Top Losers Today")
                top_loss = display_today[display_today['Day P&L (Rs)'] < 0].tail(5).iloc[::-1]
                for _, row in top_loss.iterrows():
                    st.write(f"**{row['Symbol']}** ({row['Company']}): ₹{row['Day P&L (Rs)']:+,.0f} ({row['Change (%)']:+.2f}%)")

            st.caption("Prev Close from data/latest_prices.csv | Live prices via yfinance (1-min cache)")


# ============================================================
# PAGE 4: PORTFOLIO SUMMARY
# ============================================================

elif page == "Portfolio Summary":
    st.header("Portfolio Summary Dashboard")

    st.subheader("Realized Gains/Losses")
    if not realized_df.empty:
        total_realized = realized_df['P&L'].sum()
        total_stcg = realized_df[realized_df['Gain Type'] == 'STCG']['P&L'].sum()
        total_ltcg = realized_df[realized_df['Gain Type'] == 'LTCG']['P&L'].sum()
        col1, col2, col3 = st.columns(3)
        col1.metric("Total Realized P&L", f"₹{total_realized:,.0f}")
        col2.metric("Realized STCG", f"₹{total_stcg:,.0f}")
        col3.metric("Realized LTCG", f"₹{total_ltcg:,.0f}")

        st.divider()
        scrip_pnl = realized_df.groupby('Symbol')['P&L'].sum().sort_values(ascending=False)
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("Top Gainers (Realized)")
            gainers = scrip_pnl[scrip_pnl > 0].head(5)
            for sym, pnl in gainers.items():
                st.write(f"**{sym}**: ₹{pnl:,.0f}")
        with col2:
            st.subheader("Top Losers (Realized)")
            losers = scrip_pnl[scrip_pnl < 0].tail(5)
            for sym, pnl in losers.items():
                st.write(f"**{sym}**: ₹{pnl:,.0f}")

    st.divider()
    st.subheader("Current Holdings Allocation")
    if holdings:
        with st.spinner("Fetching prices..."):
            current_prices = fetch_current_prices(list(holdings.keys()))

        alloc_data = []
        for symbol, lots in holdings.items():
            total_qty = sum(lot['qty'] for lot in lots)
            if total_qty == 0:
                continue
            current_price = current_prices.get(symbol, 0)
            value = current_price * total_qty
            if value > 0:
                alloc_data.append({'Symbol': symbol, 'Value': value})

        if alloc_data:
            alloc_df = pd.DataFrame(alloc_data).sort_values('Value', ascending=False)
            st.bar_chart(alloc_df.set_index('Symbol')['Value'])
            alloc_df['% of Portfolio'] = alloc_df['Value'] / alloc_df['Value'].sum() * 100
            alloc_df['Value'] = alloc_df['Value'].apply(lambda x: f"₹{x:,.0f}")
            alloc_df['% of Portfolio'] = alloc_df['% of Portfolio'].apply(lambda x: f"{x:.1f}%")
            st.dataframe(alloc_df, use_container_width=True, hide_index=True)

    st.divider()
    st.subheader("Transaction Statistics")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Transactions", f"{len(df)}")
    col2.metric("Unique Scrips", f"{df['Stock Symbol'].nunique()}")
    col3.metric("Buy Transactions", f"{len(df[df['Action']=='Buy'])}")
    col4.metric("Sell Transactions", f"{len(df[df['Action']=='Sell'])}")
    st.write(f"**Period:** {df['Transaction Date'].min().strftime('%d-%b-%Y')} to {df['Transaction Date'].max().strftime('%d-%b-%Y')}")
