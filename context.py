"""
Price-action context for alerts: candlestick pattern of the signal candle,
market structure (swing highs/lows, trend, BOS/CHoCH), and the exact level that
must break to enter. All derived from OHLC — no extra dependencies.

Convention: index -1 is the still-forming candle, so the last CLOSED candle is -2
(same as scanner.entry_signal).
"""
import numpy as np


# ----------------------------------------------------------- candlesticks
def candlestick_label(df, direction):
    """Describe the last closed candle in the context of the trade direction."""
    o = df["open"].iloc[-2]
    h = df["high"].iloc[-2]
    l = df["low"].iloc[-2]
    c = df["close"].iloc[-2]
    po = df["open"].iloc[-3]
    pc = df["close"].iloc[-3]

    rng = max(h - l, 1e-9)
    body = abs(c - o)
    upper = h - max(o, c)
    lower = min(o, c) - l
    bull = c > o

    # engulfing
    if bull and pc < po and o <= pc and c >= po:
        return "Bullish Engulfing 🟢 (strong reversal/continuation)"
    if (not bull) and pc > po and o >= pc and c <= po:
        return "Bearish Engulfing 🔴 (strong reversal/continuation)"
    # marubozu / strong momentum body
    if body >= 0.8 * rng:
        return ("Green Marubozu 🟢 (strong momentum)" if bull
                else "Red Marubozu 🔴 (strong momentum)")
    # pin bar / rejection
    if lower >= 2 * body and upper < body:
        return "Hammer / bullish pin bar 🔨 (demand rejection)"
    if upper >= 2 * body and lower < body:
        return "Shooting star / bearish pin bar ⭐ (supply rejection)"
    # doji
    if body <= 0.1 * rng:
        return "Doji ⚖️ (indecision — weaker signal)"
    # plain continuation
    if direction == 1:
        return "Green continuation candle" if bull else "Weak (red) candle vs long bias ⚠️"
    return "Red continuation candle" if not bull else "Weak (green) candle vs short bias ⚠️"


# ----------------------------------------------------------- market structure
def _pivots(series, k, kind):
    """Boolean array: True where series[i] is a fractal high/low (k bars each side)."""
    vals = series.values
    n = len(vals)
    out = np.zeros(n, dtype=bool)
    for i in range(k, n - k):
        window = vals[i - k:i + k + 1]
        if kind == "high" and vals[i] == window.max():
            out[i] = True
        if kind == "low" and vals[i] == window.min():
            out[i] = True
    return out


def market_structure(df, k=3, lookback=120):
    """Return dict: trend, last two swing highs/lows, BOS/CHoCH note."""
    d = df.iloc[-(lookback + 5):-1]  # exclude forming candle
    sh_mask = _pivots(d["high"], k, "high")
    sl_mask = _pivots(d["low"], k, "low")
    highs = d["high"].values[sh_mask]
    lows = d["low"].values[sl_mask]

    trend = "Range / unclear"
    if len(highs) >= 2 and len(lows) >= 2:
        hh = highs[-1] > highs[-2]
        hl = lows[-1] > lows[-2]
        lh = highs[-1] < highs[-2]
        ll = lows[-1] < lows[-2]
        if hh and hl:
            trend = "Uptrend (HH + HL) 📈"
        elif lh and ll:
            trend = "Downtrend (LH + LL) 📉"

    c = df["close"].iloc[-2]
    last_sh = highs[-1] if len(highs) else np.nan
    last_sl = lows[-1] if len(lows) else np.nan

    bos = ""
    if len(highs) and c > last_sh:
        bos = "BOS up — broke last swing high ✅"
    elif len(lows) and c < last_sl:
        bos = "BOS down — broke last swing low ✅"

    return {
        "trend": trend,
        "last_swing_high": last_sh,
        "last_swing_low": last_sl,
        "bos": bos,
        "swing_highs": highs,
        "swing_lows": lows,
    }


def break_level(df, direction, ms):
    """The exact level that must break to confirm entry + the protective level."""
    c = df["close"].iloc[-2]
    highs = ms["swing_highs"]
    lows = ms["swing_lows"]
    if direction == 1:  # long: break nearest resistance above
        above = highs[highs > c]
        must_break = float(above.min()) if len(above) else float(ms["last_swing_high"])
        protect = float(lows[lows < c].max()) if len(lows[lows < c]) else float(ms["last_swing_low"])
    else:               # short: break nearest support below
        below = lows[lows < c]
        must_break = float(below.max()) if len(below) else float(ms["last_swing_low"])
        protect = float(highs[highs > c].min()) if len(highs[highs > c]) else float(ms["last_swing_high"])
    return must_break, protect


def context_block(df, direction):
    """Single-timeframe context (kept for compatibility)."""
    cs = candlestick_label(df, direction)
    ms = market_structure(df)
    must_break, protect = break_level(df, direction, ms)
    side = "above" if direction == 1 else "below"
    lines = [f"📐 Structure: {ms['trend']}"]
    if ms["bos"]:
        lines.append(f"   {ms['bos']}")
    lines.append(f"🕯️ Candle: {cs}")
    lines.append(f"🎯 Must break: <b>{must_break:.6g}</b> ({side}) to confirm")
    lines.append(f"🛡️ Structure invalidation near: {protect:.6g}")
    return "\n".join(lines), must_break, protect


def mtf_context_block(df4, df15, direction):
    """Multi-timeframe: 4H market structure (HH/HL) + 15M price-action entry.
    Returns (text, must_break_15m, invalidation_15m)."""
    ms4 = market_structure(df4)
    ms15 = market_structure(df15)
    cs = candlestick_label(df15, direction)
    must_break, protect = break_level(df15, direction, ms15)
    side = "above" if direction == 1 else "below"

    sh4, sl4 = ms4["last_swing_high"], ms4["last_swing_low"]
    lines = [
        f"📐 <b>4H structure</b>: {ms4['trend']}",
        f"   last swing high {sh4:.6g} · last swing low {sl4:.6g}",
    ]
    if ms4["bos"]:
        lines.append(f"   {ms4['bos']}")
    lines.append("")
    lines.append(f"🎯 <b>15M entry</b> — price action")
    lines.append(f"🕯️ Candle: {cs}")
    lines.append(f"   15M structure: {ms15['trend']}")
    if ms15["bos"]:
        lines.append(f"   {ms15['bos']}")
    lines.append(f"➡️ Must break: <b>{must_break:.6g}</b> ({side}) to enter")
    lines.append(f"🛡️ Invalidation near: {protect:.6g}")
    return "\n".join(lines), must_break, protect
