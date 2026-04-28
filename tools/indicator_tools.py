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


def _heikin_ashi(df: pd.DataFrame) -> pd.DataFrame:
    ha_close = (df["Open"] + df["High"] + df["Low"] + df["Close"]) / 4
    ha_open = pd.Series(index=df.index, dtype="float64")
    if not df.empty:
        ha_open.iloc[0] = (df["Open"].iloc[0] + df["Close"].iloc[0]) / 2
        for i in range(1, len(df)):
            ha_open.iloc[i] = (ha_open.iloc[i - 1] + ha_close.iloc[i - 1]) / 2
    ha_high = pd.concat([df["High"], ha_open, ha_close], axis=1).max(axis=1)
    ha_low = pd.concat([df["Low"], ha_open, ha_close], axis=1).min(axis=1)
    return pd.DataFrame(
        {
            "ha_open": ha_open,
            "ha_high": ha_high,
            "ha_low": ha_low,
            "ha_close": ha_close,
        }
    )


def _renko_bricks(close: pd.Series, brick_size: float) -> list[tuple[str, float]]:
    if close.empty:
        return []
    bricks: list[tuple[str, float]] = []
    last_brick = float(close.iloc[0])
    for price in close.iloc[1:]:
        price = float(price)
        while price >= last_brick + brick_size:
            last_brick += brick_size
            bricks.append(("UP", last_brick))
        while price <= last_brick - brick_size:
            last_brick -= brick_size
            bricks.append(("DOWN", last_brick))
    return bricks


def _standardize(arr: np.ndarray) -> np.ndarray:
    mean = np.nanmean(arr, axis=0)
    std = np.nanstd(arr, axis=0)
    std = np.where(std == 0, 1.0, std)
    return (arr - mean) / std


def _simple_kmeans(points: np.ndarray, k: int, max_iter: int = 80) -> tuple[np.ndarray, np.ndarray]:
    """Small dependency-free k-means for deterministic clustering fallback."""
    n = len(points)
    if n == 0:
        raise ValueError("No points to cluster")
    if k < 2:
        raise ValueError("k must be >= 2")
    if n < k:
        raise ValueError("Not enough observations for requested clusters")

    order = np.argsort(points[:, 0])
    seeds = np.linspace(0, n - 1, k, dtype=int)
    centers = points[order[seeds]].copy()
    labels = np.zeros(n, dtype=int)

    for _ in range(max_iter):
        dists = ((points[:, None, :] - centers[None, :, :]) ** 2).sum(axis=2)
        new_labels = dists.argmin(axis=1)
        if np.array_equal(new_labels, labels):
            break
        labels = new_labels
        next_centers = []
        for cid in range(k):
            cluster = points[labels == cid]
            next_centers.append(cluster.mean(axis=0) if len(cluster) else centers[cid])
        centers = np.vstack(next_centers)
    return labels, centers


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


@tool
def calculate_heikin_ashi_rsi(ticker: str, rsi_window: int = 14, smoothing: int = 3) -> str:
    """Calculate a Heikin-Ashi smoothed RSI. Useful for noise-reduced momentum and regime view."""
    df = _load(ticker)
    ha = _heikin_ashi(df)
    smoothed_close = ha["ha_close"].ewm(span=smoothing, adjust=False).mean()
    ha_rsi = _rsi(smoothed_close, rsi_window).dropna()
    val = float(ha_rsi.iloc[-1])
    signal = "BULLISH" if val > 55 else "BEARISH" if val < 45 else "NEUTRAL"
    return (
        f"HeikinAshiRSI({rsi_window},{smoothing}) = {round(val, 2)} "
        f"(centered vs 50) → {signal}"
    )


@tool
def calculate_renko(ticker: str, percentage_brick_size: float = 0.5) -> str:
    """Calculate a simple percentage-based Renko structure. Useful for time-noise reduction."""
    df = _load(ticker)
    if df.empty:
        raise ValueError(f"No OHLCV data for {ticker!r}")
    brick_size = float(df["Close"].iloc[0]) * (percentage_brick_size / 100.0)
    if brick_size <= 0:
        raise ValueError("Brick size must be positive")
    bricks = _renko_bricks(df["Close"], brick_size)
    if not bricks:
        return f"Renko({percentage_brick_size}%) = no completed bricks yet"
    last_dir = bricks[-1][0]
    streak = 1
    for direction, _ in reversed(bricks[:-1]):
        if direction == last_dir:
            streak += 1
        else:
            break
    last_price = bricks[-1][1]
    return (
        f"Renko({percentage_brick_size}%): bricks={len(bricks)}, "
        f"last={last_dir}, streak={streak}, last_brick={_fmt(last_price)}"
    )


@tool
def calculate_garch_volatility(
    ticker: str,
    p: int = 1,
    q: int = 1,
    lookback: int = 400,
    forecast_horizon: int = 5,
) -> str:
    """
    Estimate conditional volatility using GARCH(p,q) when available.
    Falls back to EWMA volatility if the `arch` package is unavailable.
    """
    p = max(1, int(p))
    q = max(1, int(q))
    lookback = max(120, int(lookback))
    forecast_horizon = max(1, int(forecast_horizon))

    df = _load(ticker, limit=max(lookback + 60, 500))
    returns = np.log(df["Close"]).diff().dropna()
    returns = returns.iloc[-lookback:]
    if len(returns) < 80:
        raise ValueError("Not enough return history for volatility modeling")

    ann_factor = np.sqrt(252.0)
    model_name = "GARCH"
    try:
        from arch import arch_model

        scaled = returns * 100.0
        model = arch_model(
            scaled,
            mean="Zero",
            vol="GARCH",
            p=p,
            q=q,
            dist="normal",
            rescale=False,
        )
        fit = model.fit(disp="off", show_warning=False)
        cond_daily_vol = float(fit.conditional_volatility.iloc[-1]) / 100.0
        forecast_var = fit.forecast(horizon=forecast_horizon).variance.iloc[-1].values
        fwd_daily_vol = float(np.sqrt(np.maximum(forecast_var.mean(), 0.0))) / 100.0
    except Exception:
        # Robust fallback when arch is not installed or fit fails.
        model_name = "EWMA_FALLBACK"
        ewma_var = returns.pow(2).ewm(alpha=1.0 - 0.94, adjust=False).mean()
        cond_daily_vol = float(np.sqrt(max(float(ewma_var.iloc[-1]), 0.0)))
        fwd_daily_vol = cond_daily_vol

    current_ann = cond_daily_vol * ann_factor
    fwd_ann = fwd_daily_vol * ann_factor
    rv21 = returns.rolling(21).std().dropna() * ann_factor
    if len(rv21) > 20:
        lo = float(rv21.quantile(0.33))
        hi = float(rv21.quantile(0.67))
        regime = "HIGH_VOL" if current_ann > hi else "LOW_VOL" if current_ann < lo else "MID_VOL"
    else:
        regime = "MID_VOL"

    return (
        f"{model_name}({p},{q}): annualized_vol={round(current_ann * 100, 2)}%, "
        f"forecast_{forecast_horizon}d={round(fwd_ann * 100, 2)}% → {regime}"
    )


@tool
def calculate_volatility_regime_clustering(
    ticker: str,
    n_clusters: int = 3,
    lookback: int = 300,
    vol_window: int = 20,
) -> str:
    """
    Cluster return regimes using volatility/trend/flow features.
    Uses deterministic k-means without external ML dependencies.
    """
    n_clusters = max(2, min(int(n_clusters), 6))
    lookback = max(120, int(lookback))
    vol_window = max(10, int(vol_window))

    df = _load(ticker, limit=max(lookback + vol_window + 80, 520))
    close = df["Close"]
    ret = close.pct_change()
    feat = pd.DataFrame(
        {
            "rv": ret.rolling(vol_window).std(),
            "mom10": ret.rolling(10).mean(),
            "abs5": ret.abs().rolling(5).mean(),
            "vol_flow": df["Volume"].pct_change().rolling(5).mean(),
        }
    ).dropna()
    feat = feat.iloc[-lookback:]
    if len(feat) < n_clusters * 12:
        raise ValueError("Not enough observations for regime clustering")

    x = _standardize(feat.values.astype(float))
    labels, _ = _simple_kmeans(x, n_clusters)
    feat = feat.assign(cluster=labels)

    # Rank clusters by realized volatility so regime names are stable.
    cluster_rv = feat.groupby("cluster")["rv"].mean().sort_values()
    rank_map = {cid: idx for idx, cid in enumerate(cluster_rv.index)}
    regime_names = {
        0: "LOW_VOL",
        max(1, n_clusters // 2): "MID_VOL",
        n_clusters - 1: "HIGH_VOL",
    }

    current_cluster = int(feat["cluster"].iloc[-1])
    current_rank = rank_map[current_cluster]
    current_name = regime_names.get(current_rank, f"VOL_REGIME_{current_rank}")
    counts = feat["cluster"].value_counts().to_dict()
    rv_now = float(feat["rv"].iloc[-1]) * np.sqrt(252.0)
    mom_now = float(feat["mom10"].iloc[-1])

    return (
        f"VolRegimeCluster(k={n_clusters},w={vol_window}): current={current_name}, "
        f"ann_rv={round(rv_now * 100, 2)}%, mom10={round(mom_now * 100, 2)}%, "
        f"cluster_counts={counts}"
    )


@tool
def calculate_price_level_clustering(
    ticker: str,
    n_clusters: int = 4,
    lookback: int = 260,
) -> str:
    """
    Cluster close prices into structural levels for support/resistance context.
    """
    n_clusters = max(2, min(int(n_clusters), 8))
    lookback = max(120, int(lookback))

    df = _load(ticker, limit=max(lookback + 50, 380))
    close = df["Close"].dropna().iloc[-lookback:]
    if len(close) < n_clusters * 10:
        raise ValueError("Not enough close observations for level clustering")

    points = close.values.reshape(-1, 1).astype(float)
    labels, centers = _simple_kmeans(points, n_clusters)
    levels = sorted(float(c[0]) for c in centers)
    last = float(close.iloc[-1])

    below = [lvl for lvl in levels if lvl <= last]
    above = [lvl for lvl in levels if lvl >= last]
    support = max(below) if below else levels[0]
    resistance = min(above) if above else levels[-1]
    nearest = min(levels, key=lambda lv: abs(lv - last))
    dist_pct = abs(last - nearest) / max(abs(last), 1e-12) * 100

    return (
        f"PriceLevelCluster(k={n_clusters}): close={_fmt(last)}, "
        f"support={_fmt(support)}, resistance={_fmt(resistance)}, "
        f"nearest_level={_fmt(nearest)} ({round(dist_pct, 2)}% away), "
        f"levels={[round(v, 4) for v in levels]}"
    )


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
    calculate_heikin_ashi_rsi,
    calculate_renko,
    calculate_garch_volatility,
    calculate_volatility_regime_clustering,
    calculate_price_level_clustering,
]


def get_all_indicator_tools():
    return ALL_INDICATOR_TOOLS


INDICATOR_TOOL_PLAYBOOK = [
    (
        "calculate_rsi",
        "Bounded momentum and mean reversion",
        "Range-bound markets, exhaustion checks, divergence confirmation",
        "Do not use as the only signal in a strong trend",
    ),
    (
        "calculate_macd",
        "Trend and momentum regime change",
        "Crossovers, acceleration, transition from bearish to bullish or vice versa",
        "Can lag in fast reversals",
    ),
    (
        "calculate_bollinger_bands",
        "Volatility compression/expansion and stretch detection",
        "Breakouts, squeezes, mean reversion, band walks",
        "Use with a trend filter to avoid fading strong trends too early",
    ),
    (
        "calculate_atr",
        "Volatility and risk sizing",
        "Stop placement, position sizing, breakout range context",
        "Not a directional signal by itself",
    ),
    (
        "calculate_adx",
        "Trend strength and regime filter",
        "Decide whether to trend-follow or mean-revert",
        "Not directional by itself",
    ),
    (
        "calculate_sma",
        "Slow trend filter and support/resistance proxy",
        "Trend confirmation, mean reversion, crossover structure",
        "Too slow for fresh inflection timing on its own",
    ),
    (
        "calculate_ema",
        "Faster trend filter and dynamic support/resistance",
        "Momentum confirmation, crossovers, trailing trend bias",
        "Can whipsaw in choppy markets",
    ),
    (
        "calculate_vwap",
        "Volume-weighted fair value anchor",
        "Intraday or anchored bias, participation quality, breakout acceptance",
        "Mostly useful when price/volume context matters",
    ),
    (
        "calculate_ichimoku",
        "Multi-part trend, regime, and cloud structure",
        "Support/resistance, trend regime, breakout continuation",
        "Best when you want a fuller structural view than RSI",
    ),
    (
        "calculate_supertrend",
        "Noise-reduced trend following and trailing stops",
        "Breakout confirmation, trend persistence, invalidation levels",
        "Can be late in very tight ranges",
    ),
    (
        "calculate_wt_oscillator",
        "Smoother momentum turn detection",
        "Momentum crossovers, early turn signals, short-horizon timing",
        "Should be paired with a trend or regime filter",
    ),
    (
        "calculate_heikin_ashi_rsi",
        "Noise-reduced momentum and trend read",
        "Cleaner regime view when candles are noisy",
        "Do not use as the only confirmation in a choppy market",
    ),
    (
        "calculate_renko",
        "Time-noise reduction and structural trend view",
        "Directional persistence, brick progression, breakout structure",
        "Not a standalone valuation or volatility signal",
    ),
    (
        "calculate_garch_volatility",
        "Conditional volatility and forward risk regime",
        "Volatility clustering, leverage effects, regime-aware risk sizing",
        "Not a directional entry signal by itself",
    ),
    (
        "calculate_volatility_regime_clustering",
        "Unsupervised volatility/trend regime detection",
        "Segmenting market states beyond fixed thresholds",
        "Needs enough history and should be paired with directional structure",
    ),
    (
        "calculate_price_level_clustering",
        "Support/resistance extraction from clustered price structure",
        "Finding statistically recurring price zones",
        "Should be combined with momentum/trend confirmation",
    ),
]


def get_indicator_tool_playbook() -> str:
    lines = [
        "Indicator tool playbook:",
        "| Tool | Best use | Useful when | Avoid using alone |",
        "| --- | --- | --- | --- |",
    ]
    for tool_name, best_use, useful_when, avoid in INDICATOR_TOOL_PLAYBOOK:
        lines.append(f"| `{tool_name}` | {best_use} | {useful_when} | {avoid} |")
    lines.extend(
        [
            "",
            "Selection rules:",
            "- Do not default to RSI. Use a regime filter first when possible.",
            "- For strong trends: combine ADX with EMA/SMA, Ichimoku, or SuperTrend.",
            "- For range-bound conditions: pair RSI with Bollinger Bands and often VWAP.",
            "- For breakout setups: combine ATR, Bollinger compression, and a trend confirmation tool.",
            "- For smoother, less noisy structure: prefer SuperTrend, Ichimoku, WaveTrend, Heikin-Ashi RSI, or Renko.",
            "- For volatility regime modeling: add GARCH or volatility regime clustering.",
            "- For structural level mapping: add price level clustering with trend/momentum confirmation.",
        ]
    )
    return "\n".join(lines)
