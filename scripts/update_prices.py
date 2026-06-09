"""Fetch latest closing prices from Yahoo Finance and update data/latest_prices.csv."""

import os
import pandas as pd
import yfinance as yf

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

    data = yf.download(all_tickers, period="5d", group_by="ticker", progress=False)

    rows = []

    for ticker in all_tickers:
        symbol = get_symbol_name(ticker)
        try:
            if len(all_tickers) == 1:
                ticker_data = data
            else:
                ticker_data = data[ticker]
            closes = ticker_data["Close"].dropna()
            if len(closes) >= 2:
                close_price = round(float(closes.iloc[-1]), 2)
                prev_close = round(float(closes.iloc[-2]), 2)
                trade_date = closes.index[-1].strftime("%Y-%m-%d")
                prev_date = closes.index[-2].strftime("%Y-%m-%d")
            elif len(closes) == 1:
                close_price = round(float(closes.iloc[-1]), 2)
                prev_close = close_price
                trade_date = closes.index[-1].strftime("%Y-%m-%d")
                prev_date = trade_date
            else:
                continue
            rows.append({
                "SYMBOL": symbol,
                "TRADE_DATE": trade_date,
                "CLOSE_PRICE": close_price,
                "PREV_DATE": prev_date,
                "PREV_CLOSE": prev_close,
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
