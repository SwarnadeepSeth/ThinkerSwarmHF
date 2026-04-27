import sqlite3, json, pandas as pd

def fetch_data(db_path):
    con = sqlite3.connect(db_path)
    df = pd.read_sql_query("SELECT symbol, date, close FROM ohlcv ORDER BY symbol, date", con)
    con.close()
    return df

def compute_sma(df, window):
    df['SMA_{}'.format(window)] = df.groupby('symbol')['close'].transform(lambda x: x.rolling(window).mean())
    return df.dropna(subset=['SMA_{}'.format(window)])

def to_json(df, window):
    records = df[['symbol', 'date', 'SMA_{}'.format(window)]].rename(columns={'SMA_{}'.format(window): 'value'}).to_dict(orient='records')
    return json.dumps(records, default=str)

if __name__ == '__main__':
    data = fetch_data('data/US_DB.db')
    result = compute_sma(data, 50)
    print(to_json(result, 50))