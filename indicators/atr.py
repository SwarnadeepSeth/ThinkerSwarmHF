
import sqlite3
import pandas as pd
import json

def calculate_atr(df, period=14):
    df = df.sort_values('date')
    df['prev_close'] = df['close'].shift(1)
    df['tr'] = df[['high', 'low', 'prev_close']].apply(
        lambda x: max(
            x['high'] - x['low'],
            abs(x['high'] - x['prev_close']) if pd.notnull(x['prev_close']) else 0,
            abs(x['low'] - x['prev_close']) if pd.notnull(x['prev_close']) else 0
        ),
        axis=1
    )
    df['atr'] = df['tr'].rolling(window=period, min_periods=period).mean()
    return df.drop(columns=['prev_close', 'tr'])

if __name__ == '__main__':
    conn = sqlite3.connect('data/US_DB.db')
    query = "SELECT symbol, date, open, high, low, close, volume FROM ohlcv"
    data = pd.read_sql_query(query, conn, parse_dates=['date'])
    conn.close()
    result_frames = []
    for symbol, group in data.groupby('symbol'):
        result_frames.append(calculate_atr(group))
    result = pd.concat(result_frames).sort_values(['symbol', 'date'])
    output = result[['symbol', 'date', 'atr']].dropna().to_dict(orient='records')
    print(json.dumps(output, default=str))
