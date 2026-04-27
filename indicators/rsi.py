
import sqlite3
import pandas as pd
import json

def compute_rsi(df, period=14):
    delta = df['close'].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1/period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(to_replace=0, method='ffill')
    rsi = 100 - (100 / (1 + rs))
    df['rsi'] = rsi
    return df

if __name__ == '__main__':
    con = sqlite3.connect('data/US_DB.db')
    query = "SELECT symbol, date, close FROM ohlcv"
    data = pd.read_sql_query(query, con)
    con.close()
    data['date'] = pd.to_datetime(data['date'])
    results = []
    for symbol, grp in data.groupby('symbol'):
        grp = grp.sort_values('date').reset_index(drop=True)
        grp = compute_rsi(grp, period=14)
        for _, row in grp.dropna(subset=['rsi']).iterrows():
            results.append({
                "symbol": symbol,
                "date": row['date'].strftime('%Y-%m-%d'),
                "rsi": round(row['rsi'], 2)
            })
    print(json.dumps(results, indent=2))
