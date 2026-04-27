
import sqlite3
import pandas as pd
import json
from arch.univariate import ConstantMean, GARCH

def get_data(db_path):
    conn = sqlite3.connect(db_path)
    df = pd.read_sql_query("SELECT symbol, date, close FROM ohlcv", conn, parse_dates=["date"])
    conn.close()
    return df

def compute_garch(series):
    am = ConstantMean(series)
    am.volatility = GARCH(p=1, q=1)
    res = am.fit(disp='off')
    return res.conditional_volatility

if __name__ == '__main__':
    data = get_data('data/US_DB.db')
    results = []
    for symbol, grp in data.groupby('symbol'):
        grp = grp.sort_values('date')
        vol = compute_garch(grp['close'])
        latest = vol.iloc[-1]
        latest_date = grp['date'].iloc[-1].strftime('%Y-%m-%d')
        results.append({
            "symbol": symbol,
            "date": latest_date,
            "garch_volatility": float(latest)
        })
    print(json.dumps(results, indent=2))
