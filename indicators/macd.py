
import sqlite3
import pandas as pd
import json

def calculate_macd(df, fast=12, slow=26, signal=9):
    ema_fast = df['close'].ewm(span=fast, adjust=False).mean()
    ema_slow = df['close'].ewm(span=slow, adjust=False).mean()
    macd = ema_fast - ema_slow
    signal_line = macd.ewm(span=signal, adjust=False).mean()
    histogram = macd - signal_line
    return macd, signal_line, histogram

def main():
    conn = sqlite3.connect('data/US_DB.db')
    query = "SELECT symbol, date, close FROM ohlcv"
    df = pd.read_sql_query(query, conn, parse_dates=['date'])
    conn.close()
    results = []
    for symbol, group in df.groupby('symbol'):
        group = group.sort_values('date')
        macd, signal_line, histogram = calculate_macd(group)
        group = group.assign(macd=macd, signal=signal_line, histogram=histogram)
        for _, row in group.iterrows():
            results.append({
                "symbol": row["symbol"],
                "date": row["date"].isoformat(),
                "macd": round(row["macd"], 6),
                "signal": round(row["signal"], 6),
                "histogram": round(row["histogram"], 6)
            })
    print(json.dumps(results, indent=2))

if __name__ == '__main__':
    main()
