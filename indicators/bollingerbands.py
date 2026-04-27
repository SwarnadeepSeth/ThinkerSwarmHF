
import sqlite3
import pandas as pd
import json

def bollinger_bands(df, window=20, k=2):
    df = df.sort_values('date')
    df['bb_middle'] = df['close'].rolling(window).mean()
    df['bb_std'] = df['close'].rolling(window).std()
    df['bb_upper'] = df['bb_middle'] + k * df['bb_std']
    df['bb_lower'] = df['bb_middle'] - k * df['bb_std']
    return df.dropna(subset=['bb_middle'])

if __name__ == '__main__':
    con = sqlite3.connect('data/US_DB.db')
    df = pd.read_sql_query('SELECT symbol, date, close FROM ohlcv', con)
    df['date'] = pd.to_datetime(df['date'])
    out = []
    for sym, group in df.groupby('symbol'):
        res = bollinger_bands(group[['symbol', 'date', 'close']])
        out.extend(res[['symbol', 'date', 'bb_middle', 'bb_upper', 'bb_lower']].to_dict(orient='records'))
    print(json.dumps(out, default=str))
