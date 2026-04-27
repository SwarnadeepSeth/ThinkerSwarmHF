
import sqlite3
import pandas as pd
import json

def compute_adx(df, period=14):
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)
    tr = pd.concat([high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
    up = high.diff()
    down = -low.diff()
    plus_dm = pd.Series.where((up > down) & (up > 0), up, 0.0)
    minus_dm = pd.Series.where((down > up) & (down > 0), down, 0.0)
    atr = tr.ewm(alpha=1 / period, adjust=False).mean()
    plus_di = 100 * plus_dm.ewm(alpha=1 / period, adjust=False).mean() / atr
    minus_di = 100 * minus_dm.ewm(alpha=1 / period, adjust=False).mean() / atr
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di)
    adx = dx.ewm(alpha=1 / period, adjust=False).mean()
    return adx

if __name__ == "__main__":
    conn = sqlite3.connect("data/US_DB.db")
    query = "SELECT symbol, date, high, low, close