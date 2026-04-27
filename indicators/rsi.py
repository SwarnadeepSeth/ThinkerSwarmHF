
#!/usr/bin/env python
"""
Calculate a set of technical indicators for META from a SQLite OHLCV database.

Indicators
----------
* RSI(14)
* MACD(12,26,9) – MACD line, signal line and histogram
* Bollinger Bands (20, 2) – lower, middle, upper
* ATR(14)
* GARCH(1,1) – conditional volatility of log‑returns
* ADX(14)
* EMA(20)

The script reads the table ``ohlcv`` from ``data/US_DB.db`` (column *symbol*,
*date*, *open*, *high*, *low*, *close*, *volume*), computes the series and
outputs a JSON document that contains the date and every indicator value.
"""

import json
import sqlite3
from pathlib import Path

import pandas as pd

# ----------------------------------------------------------------------
# 3rd‑party libraries used for the calculations
# ----------------------------------------------------------------------
#   pandas‑ta  :  pip install pandas-ta
#   arch       :  pip install arch
# If you do not have them, install before running the script.
# ----------------------------------------------------------------------
import pandas_ta as ta
from arch import arch_model


def load_ohlcv(db_path: Path, symbol: str) -> pd.DataFrame:
    """Read OHLCV rows for *symbol* from the SQLite DB."""
    sql = """
        SELECT date, open, high, low, close, volume
        FROM ohlcv
        WHERE symbol = ?
        ORDER BY date
    """
    conn = sqlite3.connect(db_path)
    df = pd.read_sql_query(sql, conn, params=(symbol,))
    conn.close()
    return df


# ----------------------------------------------------------------------
# Helper functions for the technical indicators
# ----------------------------------------------------------------------
def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Calculate all required technical indicators and return a DataFrame."""
    df = df.copy()
    df.set_index('date', inplace=True)

    # RSI
    df['RSI_14'] = ta.rsi(df['close'], length=14)

    # MACD
    macd = ta.macd(df['close'], fast=12, slow=26, signal=9)
    df['MACD'] = mac