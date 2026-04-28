# -------------------------
# Indicator functions
# -------------------------

import numpy as np
import pandas as pd
import talib
import pandas_ta as ta
from renko import Renko
from prophet import Prophet

# ===========================================================================================
# Calculate Moving Average
def moving_average(df, type, price, window):
    name = type+str(window)
    if type == 'SMA':
        df[name] = df[price].rolling(window=window).mean()
    elif type == 'EMA':
        df[name] = df[price].ewm(span=window, adjust=False).mean()
    elif type == 'WMA':
        weights = np.arange(1, window+1)
        df[name] = df[price].rolling(window).apply(lambda prices: np.dot(prices, weights)/weights.sum(), raw=True)
    elif type == 'HMA':
        wma1 = 2 * df[price].rolling(window=int(window/2)).mean() - df[price].rolling(window=window).mean()
        df[name] = wma1.rolling(window=int(np.sqrt(window))).mean()
    elif type == 'RMA':
        df[name] = ta.rma(df[price], timeperiod=window)
    return df

# ===========================================================================================
# Calculate MACD
def custom_MACD (df):
    # Calculate Fast EMA and Slow EMA
    df['fast_ema'] = df['Close'].ewm(span=12).mean()
    df['slow_ema'] = df['Close'].ewm(span=26).mean()
    df['macd'] = df['fast_ema'] - df['slow_ema']
    
    # Calculate Signal Line
    df['signal_line'] = df['macd'].ewm(span=9).mean()
    
    # Calculate MACD Histogram
    df['macd_histogram'] = df['macd'] - df['signal_line']
    
    return df

def MACD(df, fast_period=12, slow_period=26, signal_period=9):
    df['macd'], df['signal_line'], df['macd_histogram'] = talib.MACD(df['Close'], fastperiod=fast_period, slowperiod=slow_period, signalperiod=signal_period)
    return df

# ===========================================================================================
# Calculate RSI
def RSI(df, window=14):
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))

    df['rsi'] = rsi
    return df

# ===========================================================================================
# Calculate VWAP anchored at the start of the day
def VWAP(df):
    df['cum_volume'] = df['Volume'].cumsum()
    df['cum_volume_price'] = df['Volume'] * df['Close']
    df['cum_volume_price'] = df['cum_volume_price'].cumsum()
    df['vwap'] = df['cum_volume_price'] / df['cum_volume']
    return df

# ===========================================================================================
# Calculate WT Oscillator
def WT_oscillator (df, n1, n2):
    # Calculate ap (typical price)
    ap = (df['High'] + df['Low'] + df['Close']) / 3
    
    # Calculate esa (exponential moving average of ap)
    esa = talib.EMA(ap, timeperiod=n1)
    
    # Calculate d (EMA of absolute difference between ap and esa)
    d = talib.EMA(abs(ap - esa), timeperiod=n1)
    
    # Calculate ci (channel index)
    ci = (ap - esa) / (0.015 * d)
    
    # Calculate tci (EMA of ci)
    tci = talib.EMA(ci, timeperiod=n2)
    
    # Calculate wt1 (weight 1) and wt2 (weight 2)
    wt1 = tci
    wt2 = talib.SMA(wt1, timeperiod=4)

    df['wt1'] = wt1
    df['wt2'] = wt2
    
    return df

# ===========================================================================================
# Calculate ATR (Average True Range)
def ATR(df, window):
    df['h-l'] = df['High'] - df['Low']
    df['h-yc'] = abs(df['High'] - df['Close'].shift(1))
    df['l-yc'] = abs(df['Low'] - df['Close'].shift(1))
    df['tr'] = df[['h-l', 'h-yc', 'l-yc']].max(axis=1)
    df['ATR'] = df['tr'].rolling(window=window).mean()
    df.drop(['h-l', 'h-yc', 'l-yc'], axis=1, inplace=True)
    return df

# ===========================================================================================
# SuperTrend Indicator 
def SuperTrend(df, period, multiplier):
    # Compute basic upper and lower bands
    df['basic_ub'] = (df['High'] + df['Low']) / 2 + multiplier * df['ATR']
    df['basic_lb'] = (df['High'] + df['Low']) / 2 - multiplier * df['ATR']
    
    # Compute final upper and lower bands
    df['final_ub'] = 0.00
    df['final_lb'] = 0.00
    for i in range(period, len(df)):
        df['final_ub'].iat[i] = df['basic_ub'].iat[i] if df['basic_ub'].iat[i] < df['final_ub'].iat[i - 1] or df['Close'].iat[i - 1] > df['final_ub'].iat[i - 1] else df['final_ub'].iat[i - 1]
        df['final_lb'].iat[i] = df['basic_lb'].iat[i] if df['basic_lb'].iat[i] > df['final_lb'].iat[i - 1] or df['Close'].iat[i - 1] < df['final_lb'].iat[i - 1] else df['final_lb'].iat[i - 1]
    
    # Set the Supertrend value
    df['supertrend'] = 0.00
    for i in range(period, len(df)):
        df['supertrend'].iat[i] = df['final_ub'].iat[i] if df['supertrend'].iat[i - 1] == df['final_ub'].iat[i - 1] and df['Close'].iat[i] <= df['final_ub'].iat[i] else \
                                df['final_lb'].iat[i] if df['supertrend'].iat[i - 1] == df['final_ub'].iat[i - 1] and df['Close'].iat[i] > df['final_ub'].iat[i] else \
                                df['final_lb'].iat[i] if df['supertrend'].iat[i - 1] == df['final_lb'].iat[i - 1] and df['Close'].iat[i] >= df['final_lb'].iat[i] else \
                                df['final_ub'].iat[i] if df['supertrend'].iat[i - 1] == df['final_lb'].iat[i - 1] and df['Close'].iat[i] < df['final_lb'].iat[i] else 0.00
    
    return df

# ===========================================================================================
# Calculate ADX
def ADX(df, window=14):
    df['adx'] = talib.ADX(df['High'], df['Low'], df['Close'], timeperiod=window)
    return df

# ===========================================================================================
# Bollinger Bands
def Bollinger_Bands(df, window):
    df['sma'] = df['Close'].rolling(window=window).mean()
    df['std'] = df['Close'].rolling(window=window).std()
    df['upper_band'] = df['sma'] + 2 * df['std']
    df['lower_band'] = df['sma'] - 2 * df['std']
    return df

# ===========================================================================================
# Ichimoku Cloud
def ICHIMOKU(df):
    # Tenkan-sen (Conversion Line)
    nine_period_high = df['High'].rolling(window=9).max()
    nine_period_low = df['Low'].rolling(window=9).min()
    df['tenkan_sen'] = (nine_period_high + nine_period_low) / 2

    # Kijun-sen (Base Line)
    period26_high = df['High'].rolling(window=26).max()
    period26_low = df['Low'].rolling(window=26).min()
    df['kijun_sen'] = (period26_high + period26_low) / 2

    # Senkou Span A (Leading Span A)
    df['senkou_span_a'] = ((df['tenkan_sen'] + df['kijun_sen']) / 2).shift(26)

    # Senkou Span B (Leading Span B)
    period52_high = df['High'].rolling(window=52).max()
    period52_low = df['Low'].rolling(window=52).min()
    df['senkou_span_b'] = ((period52_high + period52_low) / 2).shift(26)

    # Chikou Span (Lagging Span)
    df['chikou_span'] = df['Close'].shift(-26)
    return df

# ====================================================================================================== #
def indicator_tenkan_kijun_diff(df):
    nine_high = df['High'].rolling(9).max()
    nine_low = df['Low'].rolling(9).min()
    tenkan = (nine_high + nine_low) / 2

    period26_high = df['High'].rolling(26).max()
    period26_low = df['Low'].rolling(26).min()
    kijun = (period26_high + period26_low) / 2

    return tenkan - kijun

# ====================================================================================================== #
def rsi_tradingview(ohlc: pd.DataFrame, period: int = 14, round_rsi: bool = True):

    delta = ohlc["Close"].diff()
    up = delta.copy()
    up[up < 0] = 0
    up = pd.Series.ewm(up, alpha=1/period).mean()

    down = delta.copy()
    down[down > 0] = 0
    down *= -1
    down = pd.Series.ewm(down, alpha=1/period).mean()

    rsi = np.where(up == 0, 0, np.where(down == 0, 100, 100 - (100 / (1 + up / down))))
    return np.round(rsi, 2) if round_rsi else rsi

# Zero median RSI helper function
def zero_median_rsi(source, length):
    #return calculate_rsi_talib(source, length) - 50
    return rsi_tradingview(source, length) - 50

def harsi(df, length, smoothing):
    ha_rsi = zero_median_rsi(df, length)
    ha_close = (df['Open'] + df['High'] + df['Low'] + df['Close']) / 4

    ha_open = ((df['Open'].shift(smoothing) + df['Close'].shift(smoothing)) / 2).fillna(ha_close)
    ha_high = np.maximum(df['High'], np.maximum(ha_open, ha_close))
    ha_low = np.minimum(df['Low'], np.minimum(ha_open, ha_close))

    df['ha_Open'] = ha_open
    df['ha_High'] = ha_high
    df['ha_Low'] = ha_low
    df['ha_Close'] = ha_close

    df['ha_RSI'] = ha_rsi

    return df

# ===========================================================================================
# Renko Chart
def renko_chart(df, percentage_brick_size=0.5):
    
    # Calculate percentage-based brick size
    initial_price = df['Close'].iloc[0]
    brick_size = initial_price * (percentage_brick_size / 100)

    renko = Renko(brick_size=brick_size, data=df['Close'])
    renko.create_renko()
    renko_ohlc = pd.DataFrame(renko.bricks, columns=['date', 'open', 'close', 'type'])
    
    # Add missing columns if they do not exist
    if 'high' not in renko_ohlc.columns:
        renko_ohlc['high'] = None
    if 'low' not in renko_ohlc.columns:
        renko_ohlc['low'] = None
    
    # Fix the open, high, low, close values
    mask_upL = renko_ohlc[renko_ohlc['type'] == 'up']['low'].isna()
    mask_upL = mask_upL[mask_upL == True].index
    mask_downL = renko_ohlc[renko_ohlc['type'] == 'down']['low'].isna()
    mask_downL = mask_downL[mask_downL == True].index
    mask_upH = renko_ohlc[renko_ohlc['type'] == 'up']['high'].isna()
    mask_upH = mask_upH[mask_upH == True].index
    mask_downH = renko_ohlc[renko_ohlc['type'] == 'down']['high'].isna()
    mask_downH = mask_downH[mask_downH == True].index
    
    renko_ohlc.loc[mask_upL, 'low'] = renko_ohlc.loc[mask_upL, 'open']
    renko_ohlc.loc[mask_downL, 'low'] = renko_ohlc.loc[mask_downL, 'close']
    renko_ohlc.loc[mask_upH, 'high'] = renko_ohlc.loc[mask_upH, 'close']
    renko_ohlc.loc[mask_downH, 'high'] = renko_ohlc.loc[mask_downH, 'open']
    renko_ohlc = renko_ohlc[1:]
    return renko_ohlc

# =======================================================================================================
def indicator_renko_green_streak(df, percentage_brick_size=1.5):
    renko_df = renko_chart(df, percentage_brick_size)
    renko_df['date'] = pd.to_datetime(renko_df['date'])
    renko_df = renko_df.groupby('date').last().reset_index()
    renko_df.set_index('date', inplace=True)
    renko_df['direction'] = renko_df['type'].map({'up':1,'down':-1})

    # Compute green streak after last red
    streak = 0
    streaks = []
    for i, row in renko_df.iterrows():
        if row['direction'] == -1:
            streak = 0
        elif row['direction'] == 1:
            streak += 1
        streaks.append(streak)
    renko_df['green_streak'] = streaks

    # Reindex to df.index with ffill
    renko_df = renko_df.reindex(df.index, method='ffill').fillna(0)
    return renko_df['green_streak']

# =======================================================================================================
def forecast_proph (df_data, period_in_future=7):
    #Select the columns to be used for the analysis
    df_data = df_data[['Date', 'Close']]
    df_data = df_data.rename(columns={"Close": "y_data"})

    # =============================================================================
    df_train_prophet = df_data.copy()

    # Date variable needs to be named "ds" for prophet
    df_train_prophet = df_train_prophet.rename(columns={"Date": "ds"})

    # Target variable needs to be named "y" for prophet
    df_train_prophet = df_train_prophet.rename(columns={"y_data": "y"})

    model_prophet  = Prophet(daily_seasonality=True, yearly_seasonality=True)
    model_prophet.fit(df_train_prophet)

    df_future = model_prophet.make_future_dataframe(periods=period_in_future, freq='D')
    
    forecast_prophet = model_prophet.predict(df_future)
    # print ("Forecasted values:")
    # print ('='*70)
    #print(forecast_prophet[['ds', 'yhat', 'yhat_lower', 'yhat_upper']].round().tail(10))
    # print ('='*70)

    return forecast_prophet

# =============================================================================
def RMA(series, length):
    """Compute RMA (Wilder's Smoothing)."""
    alpha = 1 / length
    rma = np.zeros_like(series)
    rma[0] = series.iloc[0]
    for i in range(1, len(series)):
        rma[i] = alpha * series.iloc[i] + (1 - alpha) * rma[i - 1]
    return pd.Series(rma, index=series.index)