"""
Fast, parameterised backtest engine. Same confluence logic as scanner.py but
built so the optimizer can sweep decision parameters cheaply:

  - base indicators (fixed periods) are computed ONCE per symbol,
  - decision params (adx_min, zone_lookback, green_streak, strong_score, rr)
    are applied on top as cheap vector ops + a vectorised trade simulator.
"""
import numpy as np
import pandas as pd

import indicators as ind


def base_indicators(df, p):
    """Compute the expensive series once (periods fixed from config PARAMS)."""
    close = df["close"]
    ich = ind.ichimoku(df)
    _, st_dir = ind.supertrend(df, p["st_period"], p["st_mult"])
    hma = ind.hma(close, p["hma_period"])
    plus_di, minus_di, adx = ind.dmi_adx(df, p["adx_period"])
    macd_line, signal_line, _ = ind.macd(close)
    return {
        "close": close,
        "open": df["open"],
        "high": df["high"],
        "low": df["low"],
        "cloud_top": ich["cloud_top"],
        "cloud_bottom": ich["cloud_bottom"],
        "st_dir": st_dir,
        "hma": hma,
        "plus_di": plus_di,
        "minus_di": minus_di,
        "adx": adx,
        "rsi": ind.rsi(close, p["rsi_period"]),
        "macd": macd_line,
        "signal": signal_line,
        "atr": ind.atr(df, p["atr_period"]),
    }


def bias_from_base(b, adx_min):
    c = b["close"]
    above = c > b["cloud_top"]
    below = c < b["cloud_bottom"]
    hma_rising = b["hma"] > b["hma"].shift(3)
    strong = b["adx"] >= adx_min
    bull = above & (b["st_dir"] == 1) & hma_rising & strong & (b["plus_di"] > b["minus_di"])
    bear = below & (b["st_dir"] == -1) & (~hma_rising) & strong & (b["minus_di"] > b["plus_di"])
    bias = pd.Series(0, index=c.index)
    bias[bull] = 1
    bias[bear] = -1
    return bias


def scores_from_base(b, zone_lookback, green_streak, adx_min):
    c = b["close"]
    zone_high = b["high"].rolling(zone_lookback).max().shift(1)
    zone_low = b["low"].rolling(zone_lookback).min().shift(1)
    body = c - b["open"]
    green = (body > 0).rolling(green_streak).sum() == green_streak
    red = (body < 0).rolling(green_streak).sum() == green_streak

    long_score = (
        (c > zone_high).astype(int)
        + green.astype(int)
        + (b["st_dir"] == 1).astype(int)
        + ((c > b["hma"]) & (b["hma"] > b["hma"].shift(2))).astype(int)
        + (b["macd"] > b["signal"]).astype(int)
        + ((b["rsi"] > 50) & (b["rsi"] < 75)).astype(int)
        + ((b["plus_di"] > b["minus_di"]) & (b["adx"] >= adx_min)).astype(int)
    )
    short_score = (
        (c < zone_low).astype(int)
        + red.astype(int)
        + (b["st_dir"] == -1).astype(int)
        + ((c < b["hma"]) & (b["hma"] < b["hma"].shift(2))).astype(int)
        + (b["macd"] < b["signal"]).astype(int)
        + ((b["rsi"] < 50) & (b["rsi"] > 25)).astype(int)
        + ((b["minus_di"] > b["plus_di"]) & (b["adx"] >= adx_min)).astype(int)
    )
    return long_score, short_score, zone_high, zone_low


def align_bias(bias4, index15):
    """Map last-closed 4h bias onto the 15m index (returns np.array)."""
    left = pd.DataFrame({"ts": index15})
    right = bias4.shift(1).rename("bias").reset_index()
    right.columns = ["ts", "bias"]
    merged = pd.merge_asof(
        left.sort_values("ts"), right.sort_values("ts"),
        on="ts", direction="backward",
    )
    return merged["bias"].fillna(0).values


def simulate(b15, bias15, long_s, short_s, zone_high, zone_low,
             rr, strong_score, atr_mult=1.5, warmup=60, start=None, stop=None,
             cost_pct=0.0):
    """Vectorised-ish simulator. Returns np.array of trade R-multiples.
    Only entries with index in [start, stop) are taken (for train/test splits).
    cost_pct = round-trip cost (fees+slippage) as a percent of notional; it is
    converted to R per trade using that trade's stop distance and subtracted."""
    high = b15["high"].values
    low = b15["low"].values
    close = b15["close"].values
    ls = long_s.values
    ss = short_s.values
    zh = zone_high.values
    zl = zone_low.values
    atr = b15["atr"].values
    n = len(close)
    results = []
    i = max(warmup, start if start is not None else warmup)
    end = min(n - 1, stop if stop is not None else n - 1)
    while i < end:
        bsign = bias15[i]
        go_long = bsign == 1 and ls[i] >= strong_score
        go_short = bsign == -1 and ss[i] >= strong_score
        if not (go_long or go_short):
            i += 1
            continue

        entry = close[i]
        if go_long:
            stop = min(zh[i], entry) - atr_mult * atr[i]
            target = entry + (entry - stop) * rr
            fwd_lo = low[i + 1:]
            fwd_hi = high[i + 1:]
            hit_stop = np.where(fwd_lo <= stop)[0]
            hit_tgt = np.where(fwd_hi >= target)[0]
        else:
            stop = max(zl[i], entry) + atr_mult * atr[i]
            target = entry - (stop - entry) * rr
            fwd_hi = high[i + 1:]
            fwd_lo = low[i + 1:]
            hit_stop = np.where(fwd_hi >= stop)[0]
            hit_tgt = np.where(fwd_lo <= target)[0]

        s_idx = hit_stop[0] if len(hit_stop) else None
        t_idx = hit_tgt[0] if len(hit_tgt) else None
        if s_idx is None and t_idx is None:
            break  # open trade at series end
        stop_pct = abs(entry - stop) / entry
        cost_R = (cost_pct / 100.0) / stop_pct if stop_pct else 0.0
        if t_idx is not None and (s_idx is None or t_idx < s_idx):
            results.append(rr - cost_R)
            exit_off = t_idx
        else:
            results.append(-1.0 - cost_R)
            exit_off = s_idx
        i = i + 1 + exit_off + 1
    return np.array(results)


def stats(results):
    if results is None or len(results) == 0:
        return None
    arr = np.asarray(results)
    wins = arr[arr > 0]
    losses = arr[arr < 0]
    gross_loss = -losses.sum()
    pf = (wins.sum() / gross_loss) if gross_loss else float("inf")
    streak = mx = 0
    for r in arr:
        streak = streak + 1 if r < 0 else 0
        mx = max(mx, streak)
    return {
        "trades": len(arr),
        "win_rate": len(wins) / len(arr),
        "total_R": float(arr.sum()),
        "avg_R": float(arr.mean()),
        "pf": pf,
        "max_loss_streak": mx,
    }
