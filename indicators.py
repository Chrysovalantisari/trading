"""
Technical indicators implemented in pure pandas/numpy (no TA library needed).
Each function takes a DataFrame with columns: open, high, low, close, volume.
These match the indicator stack from the trader profile:
RSI, DMI/ADX, ATR, MACD, Ichimoku, Supertrend, Keltner Channels, HMA.
"""
import numpy as np
import pandas as pd


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - 100 / (1 + rs)


def true_range(df: pd.DataFrame) -> pd.Series:
    prev_close = df["close"].shift(1)
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - prev_close).abs(),
        (df["low"] - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Wilder's ATR (also serves as the 'AMR/ATR' in the profile)."""
    return true_range(df).ewm(alpha=1 / period, adjust=False).mean()


def dmi_adx(df: pd.DataFrame, period: int = 14):
    """Returns (plus_di, minus_di, adx)."""
    up = df["high"].diff()
    down = -df["low"].diff()
    plus_dm = np.where((up > down) & (up > 0), up, 0.0)
    minus_dm = np.where((down > up) & (down > 0), down, 0.0)
    plus_dm = pd.Series(plus_dm, index=df.index)
    minus_dm = pd.Series(minus_dm, index=df.index)

    atr_ = true_range(df).ewm(alpha=1 / period, adjust=False).mean()
    plus_di = 100 * plus_dm.ewm(alpha=1 / period, adjust=False).mean() / atr_
    minus_di = 100 * minus_dm.ewm(alpha=1 / period, adjust=False).mean() / atr_
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    adx = dx.ewm(alpha=1 / period, adjust=False).mean()
    return plus_di, minus_di, adx


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    """Returns (macd_line, signal_line, histogram)."""
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    return macd_line, signal_line, macd_line - signal_line


def ichimoku(df: pd.DataFrame, tenkan=9, kijun=26, senkou=52):
    """Returns dict with tenkan, kijun, senkou_a, senkou_b, cloud_top, cloud_bottom."""
    def mid(n):
        return (df["high"].rolling(n).max() + df["low"].rolling(n).min()) / 2

    t = mid(tenkan)
    k = mid(kijun)
    span_a = ((t + k) / 2).shift(kijun)
    span_b = mid(senkou).shift(kijun)
    return {
        "tenkan": t,
        "kijun": k,
        "senkou_a": span_a,
        "senkou_b": span_b,
        "cloud_top": pd.concat([span_a, span_b], axis=1).max(axis=1),
        "cloud_bottom": pd.concat([span_a, span_b], axis=1).min(axis=1),
    }


def supertrend(df: pd.DataFrame, period: int = 10, multiplier: float = 3.0):
    """Returns (supertrend_line, direction) where direction is +1 up / -1 down."""
    atr_ = atr(df, period)
    hl2 = (df["high"] + df["low"]) / 2
    upper = hl2 + multiplier * atr_
    lower = hl2 - multiplier * atr_

    final_upper = upper.copy()
    final_lower = lower.copy()
    close = df["close"]
    n = len(df)
    for i in range(1, n):
        final_upper.iloc[i] = (
            upper.iloc[i]
            if (upper.iloc[i] < final_upper.iloc[i - 1] or close.iloc[i - 1] > final_upper.iloc[i - 1])
            else final_upper.iloc[i - 1]
        )
        final_lower.iloc[i] = (
            lower.iloc[i]
            if (lower.iloc[i] > final_lower.iloc[i - 1] or close.iloc[i - 1] < final_lower.iloc[i - 1])
            else final_lower.iloc[i - 1]
        )

    direction = pd.Series(1, index=df.index)
    st = pd.Series(np.nan, index=df.index)
    for i in range(1, n):
        if close.iloc[i] > final_upper.iloc[i - 1]:
            direction.iloc[i] = 1
        elif close.iloc[i] < final_lower.iloc[i - 1]:
            direction.iloc[i] = -1
        else:
            direction.iloc[i] = direction.iloc[i - 1]
        st.iloc[i] = final_lower.iloc[i] if direction.iloc[i] == 1 else final_upper.iloc[i]
    return st, direction


def keltner(df: pd.DataFrame, period: int = 20, mult: float = 2.0):
    """Returns (upper, mid, lower)."""
    mid = df["close"].ewm(span=period, adjust=False).mean()
    rng = atr(df, period) * mult
    return mid + rng, mid, mid - rng


def wma(series: pd.Series, period: int) -> pd.Series:
    weights = np.arange(1, period + 1)
    return series.rolling(period).apply(
        lambda x: np.dot(x, weights) / weights.sum(), raw=True
    )


def hma(close: pd.Series, period: int = 21) -> pd.Series:
    """Hull Moving Average."""
    half = max(int(period / 2), 1)
    sqrt_p = max(int(np.sqrt(period)), 1)
    return wma(2 * wma(close, half) - wma(close, period), sqrt_p)


def volume_poc(df: pd.DataFrame, lookback: int = 120, bins: int = 30):
    """Simple volume-profile Point of Control over the last `lookback` bars."""
    recent = df.iloc[-lookback:]
    if recent.empty:
        return np.nan
    price = (recent["high"] + recent["low"] + recent["close"]) / 3
    hist, edges = np.histogram(price, bins=bins, weights=recent["volume"])
    idx = int(np.argmax(hist))
    return float((edges[idx] + edges[idx + 1]) / 2)
