"""
LangChain tools for technical indicator calculation.
Self-contained: no imports from indicator_functions.py to avoid missing-dep issues.
Uses pandas/numpy always; talib used where available with pandas fallback.
"""

import sqlite3
import os
import pandas as pd
import numpy as np
from langchain_core.tools import tool

# Module-level DB path — set by quant_node before invoking tools
_DB_PATH = "data/US_DB.db"


# ── Data loader ───────────────────────────────────────────────────────────────

def _load(ticker: str, limit: int = 300) -> pd.DataFrame:
    conn = sqlite3.connect(_DB_PATH)
    df = pd.read_sql_query(
        "SELECT date, open, high, low, close, volume FROM ohlcv "
        "WHERE symbol = ? ORDER BY date ASC LIMIT ?",
        conn,
        params=(ticker, limit),
    )
    conn.close()
    if df.empty:
        raise ValueError(f"No OHLCV data for {ticker!r}")
    df.columns = ["Date", "Open", "High", "Low", "Close", "Volume"]
    df["Date"] = pd.to_datetime(df["Date"])
    for col in ["Open", "High", "Low", "Close", "Volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


# ── Calculation helpers (no external deps beyond pandas/numpy/talib) ──────────

def _rsi(close: pd.Series, window: int) -> pd.Series:
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0).rolling(window).mean()
    loss = (-delta.where(delta < 0, 0.0)).rolling(window).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))


def _macd(close: pd.Series, fast=12, slow=26, signal=9):
    line = close.ewm(span=fast, adjust=False).mean() - close.ewm(span=slow, adjust=False).mean()
    sig = line.ewm(span=signal, adjust=False).mean()
    return line, sig, line - sig


def _atr(high: pd.Series, low: pd.Series, close: pd.Series, window: int) -> pd.Series:
    hl = high - low
    hc = (high - close.shift()).abs()
    lc = (low - close.shift()).abs()
    tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
    return tr.rolling(window).mean()


def _adx(high: pd.Series, low: pd.Series, close: pd.Series, window: int) -> pd.Series:
    try:
        import talib
        return pd.Series(
            talib.ADX(high.values.astype(float), low.values.astype(float), close.values.astype(float), timeperiod=window),
            index=close.index,
        )
    except ImportError:
        atr = _atr(high, low, close, window)
        p_dm = high.diff().clip(lower=0)
        m_dm = (-low.diff()).clip(lower=0)
        # keep only the dominant move
        p_dm = p_dm.where(p_dm > m_dm, 0.0)
        m_dm = m_dm.where(m_dm > p_dm.where(p_dm > m_dm, 0.0), 0.0)
        p_di = 100 * p_dm.rolling(window).mean() / atr
        m_di = 100 * m_dm.rolling(window).mean() / atr
        dx = 100 * (p_di - m_di).abs() / (p_di + m_di + 1e-10)
        return dx.rolling(window).mean()


def _ema_series(close: pd.Series, span: int) -> pd.Series:
    return close.ewm(span=span, adjust=False).mean()


def _wt(high: pd.Series, low: pd.Series, close: pd.Series, n1: int, n2: int):
    ap = (high + low + close) / 3
    try:
        import talib
        esa = pd.Series(talib.EMA(ap.values.astype(float), timeperiod=n1), index=close.index)
        d   = pd.Series(talib.EMA(np.abs((ap - esa).values.astype(float)), timeperiod=n1), index=close.index)
        ci  = (ap - esa) / (0.015 * d.replace(0, np.nan))
        wt1 = pd.Series(talib.EMA(ci.ffill().values.astype(float), timeperiod=n2), index=close.index)
        wt2 = pd.Series(talib.SMA(wt1.values.astype(float), timeperiod=4), index=close.index)
    except ImportError:
        esa = ap.ewm(span=n1, adjust=False).mean()
        d   = (ap - esa).abs().ewm(span=n1, adjust=False).mean()
        ci  = (ap - esa) / (0.015 * d.replace(0, np.nan))
        wt1 = ci.ewm(span=n2, adjust=False).mean()
        wt2 = wt1.rolling(4).mean()
    return wt1, wt2


def _fmt(v) -> str:
    try:
        return str(round(float(v), 4))
    except Exception:
        return str(v)


# ── Tools ─────────────────────────────────────────────────────────────────────

@tool
def calculate_rsi(ticker: str, window: int = 14) -> str:
    """Calculate RSI (Relative Strength Index). Returns value and OVERBOUGHT/OVERSOLD/NEUTRAL signal."""
    df = _load(ticker)
    rsi = _rsi(df["Close"], window).dropna()
    val = float(rsi.iloc[-1])
    signal = "OVERBOUGHT" if val > 70 else "OVERSOLD" if val < 30 else "NEUTRAL"
    return f"RSI({window}) = {round(val, 2)} → {signal}"


@tool
def calculate_macd(
    ticker: str,
    fast_period: int = 12,
    slow_period: int = 26,
    signal_period: int = 9,
) -> str:
    """Calculate MACD line, signal line, and histogram. Returns BULLISH/BEARISH direction."""
    df = _load(ticker)
    line, sig, hist = _macd(df["Close"], fast_period, slow_period, signal_period)
    lv, sv, hv = float(line.dropna().iloc[-1]), float(sig.dropna().iloc[-1]), float(hist.dropna().iloc[-1])
    direction = "BULLISH" if hv > 0 else "BEARISH"
    return (
        f"MACD({fast_period},{slow_period},{signal_period}): "
        f"line={_fmt(lv)}, signal={_fmt(sv)}, histogram={_fmt(hv)} → {direction}"
    )


@tool
def calculate_bollinger_bands(ticker: str, window: int = 20) -> str:
    """Calculate Bollinger Bands. Returns upper/mid/lower band values and price position."""
    df = _load(ticker)
    sma = df["Close"].rolling(window).mean()
    std = df["Close"].rolling(window).std()
    upper = (sma + 2 * std).dropna()
    mid   = sma.dropna()
    lower = (sma - 2 * std).dropna()
    close = float(df["Close"].iloc[-1])
    u, m, l = float(upper.iloc[-1]), float(mid.iloc[-1]), float(lower.iloc[-1])
    pos = "ABOVE_UPPER" if close > u else "BELOW_LOWER" if close < l else "INSIDE_BANDS"
    return (
        f"BollingerBands({window}): upper={_fmt(u)}, mid={_fmt(m)}, "
        f"lower={_fmt(l)}, close={_fmt(close)} → {pos}"
    )


@tool
def calculate_atr(ticker: str, window: int = 14) -> str:
    """Calculate ATR (Average True Range). Returns volatility in price units and as % of close."""
    df = _load(ticker)
    atr = _atr(df["High"], df["Low"], df["Close"], window).dropna()
    val  = float(atr.iloc[-1])
    close = float(df["Close"].iloc[-1])
    return f"ATR({window}) = {_fmt(val)} ({round(val/close*100, 2)}% of price)"


@tool
def calculate_adx(ticker: str, window: int = 14) -> str:
    """Calculate ADX (Average Directional Index). >25 = strong trend, <20 = weak/no trend."""
    df = _load(ticker)
    adx = _adx(df["High"], df["Low"], df["Close"], window).dropna()
    val = float(adx.iloc[-1])
    strength = "STRONG_TREND" if val > 25 else "WEAK_TREND" if val < 20 else "DEVELOPING_TREND"
    return f"ADX({window}) = {round(val, 2)} → {strength}"


@tool
def calculate_sma(ticker: str, window: int = 20) -> str:
    """Calculate SMA (Simple Moving Average). Returns value and whether price is above/below."""
    df = _load(ticker)
    sma = df["Close"].rolling(window).mean().dropna()
    val   = float(sma.iloc[-1])
    close = float(df["Close"].iloc[-1])
    return f"SMA({window}) = {_fmt(val)}, close={_fmt(close)} → price is {'ABOVE' if close > val else 'BELOW'} SMA"


@tool
def calculate_ema(ticker: str, window: int = 20) -> str:
    """Calculate EMA (Exponential Moving Average). Returns value and whether price is above/below."""
    df = _load(ticker)
    ema   = _ema_series(df["Close"], window).dropna()
    val   = float(ema.iloc[-1])
    close = float(df["Close"].iloc[-1])
    return f"EMA({window}) = {_fmt(val)}, close={_fmt(close)} → price is {'ABOVE' if close > val else 'BELOW'} EMA"


@tool
def calculate_vwap(ticker: str) -> str:
    """Calculate VWAP (Volume Weighted Average Price). Returns value and price position vs VWAP."""
    df = _load(ticker)
    vwap  = (df["Volume"] * df["Close"]).cumsum() / df["Volume"].cumsum()
    val   = float(vwap.dropna().iloc[-1])
    close = float(df["Close"].iloc[-1])
    return f"VWAP = {_fmt(val)}, close={_fmt(close)} → price is {'ABOVE' if close > val else 'BELOW'} VWAP"


@tool
def calculate_ichimoku(ticker: str) -> str:
    """
    Calculate Ichimoku Cloud (tenkan-sen, kijun-sen, senkou span A/B).
    Returns cloud bias: BULLISH/BEARISH/NEUTRAL.
    """
    df = _load(ticker, limit=400)
    h, l = df["High"], df["Low"]
    tenkan = (h.rolling(9).max()  + l.rolling(9).min())  / 2
    kijun  = (h.rolling(26).max() + l.rolling(26).min()) / 2
    span_a = ((tenkan + kijun) / 2).shift(26)
    span_b = ((h.rolling(52).max() + l.rolling(52).min()) / 2).shift(26)
    close  = float(df["Close"].iloc[-1])
    tk = float(tenkan.dropna().iloc[-1])
    kj = float(kijun.dropna().iloc[-1])
    sa = float(span_a.dropna().iloc[-1]) if not span_a.dropna().empty else float("nan")
    sb = float(span_b.dropna().iloc[-1]) if not span_b.dropna().empty else float("nan")
    top, bot = max(sa, sb), min(sa, sb)
    bias = (
        "BULLISH (above cloud)" if close > top
        else "BEARISH (below cloud)" if close < bot
        else "NEUTRAL (inside cloud)"
    )
    return (
        f"Ichimoku: tenkan={_fmt(tk)}, kijun={_fmt(kj)}, "
        f"span_a={_fmt(sa)}, span_b={_fmt(sb)} → {bias}"
    )


@tool
def calculate_supertrend(ticker: str, period: int = 10, multiplier: float = 3.0) -> str:
    """Calculate SuperTrend indicator. Returns trend value and BULLISH/BEARISH signal."""
    df = _load(ticker)
    atr = _atr(df["High"], df["Low"], df["Close"], period)
    mid = (df["High"] + df["Low"]) / 2
    basic_ub = mid + multiplier * atr
    basic_lb = mid - multiplier * atr

    final_ub = basic_ub.copy()
    final_lb = basic_lb.copy()
    for i in range(1, len(df)):
        final_ub.iat[i] = basic_ub.iat[i] if basic_ub.iat[i] < final_ub.iat[i-1] or df["Close"].iat[i-1] > final_ub.iat[i-1] else final_ub.iat[i-1]
        final_lb.iat[i] = basic_lb.iat[i] if basic_lb.iat[i] > final_lb.iat[i-1] or df["Close"].iat[i-1] < final_lb.iat[i-1] else final_lb.iat[i-1]

    supertrend = pd.Series(np.nan, index=df.index)
    for i in range(1, len(df)):
        prev_st = supertrend.iat[i-1] if not np.isnan(supertrend.iat[i-1]) else final_ub.iat[i-1]
        if prev_st == final_ub.iat[i-1]:
            supertrend.iat[i] = final_lb.iat[i] if df["Close"].iat[i] > final_ub.iat[i] else final_ub.iat[i]
        else:
            supertrend.iat[i] = final_ub.iat[i] if df["Close"].iat[i] < final_lb.iat[i] else final_lb.iat[i]

    close = float(df["Close"].iloc[-1])
    st_val = float(supertrend.dropna().iloc[-1])
    signal = "BULLISH" if close > st_val else "BEARISH"
    return f"SuperTrend({period},{multiplier}) = {_fmt(st_val)}, close={_fmt(close)} → {signal}"


@tool
def calculate_wt_oscillator(ticker: str, n1: int = 10, n2: int = 21) -> str:
    """
    Calculate Wave Trend (WT) Oscillator.
    Returns wt1, wt2, and momentum signal (bullish cross vs bearish cross).
    """
    df = _load(ticker)
    wt1, wt2 = _wt(df["High"], df["Low"], df["Close"], n1, n2)
    w1 = float(wt1.dropna().iloc[-1])
    w2 = float(wt2.dropna().iloc[-1])
    cross = "WT1_ABOVE_WT2 (bullish momentum)" if w1 > w2 else "WT1_BELOW_WT2 (bearish momentum)"
    return f"WaveTrend({n1},{n2}): wt1={round(w1,2)}, wt2={round(w2,2)} → {cross}"


# ─────────────────────────────────────────────────────────────────────────────
ALL_INDICATOR_TOOLS = [
    calculate_rsi,
    calculate_macd,
    calculate_bollinger_bands,
    calculate_atr,
    calculate_adx,
    calculate_sma,
    calculate_ema,
    calculate_vwap,
    calculate_ichimoku,
    calculate_supertrend,
    calculate_wt_oscillator,
]


def get_all_indicator_tools():
    return ALL_INDICATOR_TOOLS
