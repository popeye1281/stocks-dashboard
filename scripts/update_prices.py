"""Fetch latest closing prices from Yahoo Finance and update data/latest_prices.csv."""

import os
import pandas as pd
import yfinance as yf
from datetime import datetime

# Same ticker map as app.py
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

# Additional tickers in latest_prices.csv that aren't in portfolio TICKER_MAP
EXTRA_TICKERS = [
    "ADANIENT.NS", "ASIANPAINT.NS", "AXISBANK.NS", "HCLTECH.NS",
    "HDFCBANK.NS", "HINDUNILVR.NS", "INFY.NS", "ITC.NS", "KOTAKBANK.NS",
    "NTPC.NS", "ONGC.NS", "POWERGRID.NS", "RELIANCE.NS", "SBIN.NS",
    "SUNPHARMA.NS", "TATASTEEL.NS", "TCS.NS", "TITAN.NS", "WIPRO.NS",
]


def get_symbol_name(ticker):
    """Convert Yahoo Finance ticker to CSV symbol name."""
    return ticker.replace(".NS", "").replace(".BO", "").replace("-", "_")


def main():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    csv_path = os.path.join(base_dir, "data", "latest_prices.csv")

    all_tickers = list(TICKER_MAP.values()) + EXTRA_TICKERS
    all_tickers = list(set(all_tickers))

    print(f"Fetching prices for {len(all_tickers)} tickers...")

    data = yf.download(all_tickers, period="2d", group_by="ticker", progress=False)

    rows = []
    today = datetime.now().strftime("%Y-%m-%d")

    for ticker in all_tickers:
        symbol = get_symbol_name(ticker)
        try:
            if len(all_tickers) == 1:
                ticker_data = data
            else:
                ticker_data = data[ticker]
            close_price = ticker_data["Close"].dropna().iloc[-1]
            rows.append({
                "SYMBOL": symbol,
                "TRADE_DATE": today,
                "CLOSE_PRICE": round(float(close_price), 2),
            })
        except (KeyError, IndexError):
            print(f"  Warning: Could not fetch price for {ticker}")

    if rows:
        df = pd.DataFrame(rows).sort_values("SYMBOL").reset_index(drop=True)
        df.to_csv(csv_path, index=False)
        print(f"Updated {csv_path} with {len(df)} prices.")
    else:
        print("No prices fetched. CSV not updated.")


if __name__ == "__main__":
    main()
