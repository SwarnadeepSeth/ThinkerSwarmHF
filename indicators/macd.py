import pandas as pd
import numpy as np
import sqlite3


def calculate_macd(conn, symbol, fast=12, slow=26, signal=9):
    query = """
        SELECT date, close FROM ohlcv 
        WHERE symbol = ? 
        ORDER BY date ASC
    """
    df = pd.read_sql_query(query, conn, params=(symbol,))

    if df.empty:
        return None

    exp1 = df["close"].ewm(span=fast, adjust=False).mean()
    exp2 = df["close"].ewm(span=slow, adjust=False).mean()
    macd = exp1 - exp2
    signal_line = macd.ewm(span=signal, adjust=False).mean()
    histogram = macd - signal_line

    df["macd"] = macd
    df["signal_line"] = signal_line
    df["histogram"] = histogram

    latest = df.iloc[-1]
    return {
        "symbol": symbol,
        "date": latest["date"],
        "close": latest["close"],
        "macd": latest["macd"],
        "signal_line": latest["signal_line"],
        "histogram": latest["histogram"],
    }


if __name__ == "__main__":
    conn = sqlite3.connect("data/US_DB.db")
    symbol = "MSFT"
    result = calculate_macd(conn, symbol)

    if result:
        print(f"MACD Indicator Results for {symbol}:")
        print(f"  Date: {result['date']}")
        print(f"  Close: ${result['close']:.2f}")
        print(f"  MACD: {result['macd']:.4f}")
        print(f"  Signal: {result['signal_line']:.4f}")
        print(f"  Histogram: {result['histogram']:.4f}")

        if result["histogram"] > 0:
            print(f"  Signal: BULLISH (MACD above signal)")
        else:
            print(f"  Signal: BEARISH (MACD below signal)")

        assert not np.isnan(result["macd"]), "MACD should not be NaN"
        assert not np.isnan(result["signal_line"]), "Signal should not be NaN"
        print("  Tests: PASSED")
    else:
        print(f"No data found for {symbol}")

    conn.close()
