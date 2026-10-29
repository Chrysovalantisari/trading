"""
Backtest YOUR confluence rules on historical data.

For each symbol it reconstructs, bar by bar:
  - the 4h trend bias,
  - the 15m STRONG trigger (zone break + candle continuation + indicator confluence),
simulates the trade (stop = zone +/- 1.5xATR, target = R:R x stop distance),
and reports win rate, average R, total R, profit factor and max losing streak.

This is an APPROXIMATION (bar-close fills, no fees/funding/slippage). It tells you
whether the edge is plausible — not what you'll actually make. Run:

    python backtest.py              # default history
    python backtest.py 2000         # pull 2000 candles per timeframe
"""
import sys
import pandas as pd
import numpy as np

import config as C
import indicators as ind

try:
    import ccxt
except ImportError:
    sys.exit("ccxt not installed. Run ./run.sh first.")

CANDLES = int(sys.argv[1]) if len(sys.argv) > 1 else 1500


def make_exchange():
    return getattr(ccxt, C.EXCHANGE)({
        "enableRateLimit": True,
        "options": {"defaultType": C.MARKET_TYPE},
    })


def fetch(ex, symbol, timeframe, limit):
    o = ex.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
    df = pd.DataFrame(o, columns=["ts", "open", "high", "low", "close", "volume"])
    df["ts"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    return df.set_index("ts")


def bias_series(df):
    """Per-bar 4h bias (+1/-1/0), as known at each bar's close."""
    p = C.PARAMS
    ich = ind.ichimoku(df)
    _, st_dir = ind.supertrend(df, p["st_period"], p["st_mult"])
    hma = ind.hma(df["close"], p["hma_period"])
    plus_di, minus_di, adx = ind.dmi_adx(df, p["adx_period"])
    c = df["close"]

    above = c > ich["cloud_top"]
    below = c < ich["cloud_bottom"]
    hma_rising = hma > hma.shift(3)
    strong = adx >= p["adx_min"]
    bull = above & (st_dir == 1) & hma_rising & strong & (plus_di > minus_di)
    bear = below & (st_dir == -1) & (~hma_rising) & strong & (minus_di > plus_di)
    bias = pd.Series(0, index=df.index)
    bias[bull] = 1
    bias[bear] = -1
    return bias


def entry_scores(df):
    """Per-bar long_score and short_score (0..7) plus helper arrays."""
    p = C.PARAMS
    close = df["close"]
    zone_high = df["high"].rolling(p["zone_lookback"]).max().shift(1)
    zone_low = df["low"].rolling(p["zone_lookback"]).min().shift(1)

    rsi = ind.rsi(close, p["rsi_period"])
    macd_line, signal_line, _ = ind.macd(close)
    _, st_dir = ind.supertrend(df, p["st_period"], p["st_mult"])
    hma = ind.hma(close, p["hma_period"])
    plus_di, minus_di, adx = ind.dmi_adx(df, p["adx_period"])
    atr = ind.atr(df, p["atr_period"])

    body = close - df["open"]
    green = body > 0
    red = body < 0
    k = p["green_streak"]
    bull_streak = green.rolling(k).sum() == k
    bear_streak = red.rolling(k).sum() == k

    long_checks = pd.concat([
        close > zone_high,
        bull_streak,
        st_dir == 1,
        (close > hma) & (hma > hma.shift(2)),
        macd_line > signal_line,
        (rsi > 50) & (rsi < 75),
        (plus_di > minus_di) & (adx >= p["adx_min"]),
    ], axis=1)
    short_checks = pd.concat([
        close < zone_low,
        bear_streak,
        st_dir == -1,
        (close < hma) & (hma < hma.shift(2)),
        macd_line < signal_line,
        (rsi < 50) & (rsi > 25),
        (minus_di > plus_di) & (adx >= p["adx_min"]),
    ], axis=1)

    return {
        "long": long_checks.sum(axis=1),
        "short": short_checks.sum(axis=1),
        "zone_high": zone_high,
        "zone_low": zone_low,
        "atr": atr,
    }


def simulate(df, bias_15m, scores):
    """Walk forward; return list of trade R-multiples."""
    rr = C.ACCOUNT["target_rr"]
    highs, lows, closes = df["high"].values, df["low"].values, df["close"].values
    n = len(df)
    results = []
    i = 60  # warmup
    while i < n - 1:
        b = bias_15m.iloc[i]
        if b == 1 and scores["long"].iloc[i] >= C.STRONG_SCORE:
            entry = closes[i]
            stop = min(scores["zone_high"].iloc[i], entry) - 1.5 * scores["atr"].iloc[i]
            target = entry + (entry - stop) * rr
            j = i + 1
            while j < n:
                if lows[j] <= stop:
                    results.append(-1.0); break
                if highs[j] >= target:
                    results.append(rr); break
                j += 1
            i = j + 1
            continue
        if b == -1 and scores["short"].iloc[i] >= C.STRONG_SCORE:
            entry = closes[i]
            stop = max(scores["zone_low"].iloc[i], entry) + 1.5 * scores["atr"].iloc[i]
            target = entry - (stop - entry) * rr
            j = i + 1
            while j < n:
                if highs[j] >= stop:
                    results.append(-1.0); break
                if lows[j] <= target:
                    results.append(rr); break
                j += 1
            i = j + 1
            continue
        i += 1
    return results


def stats(results):
    if not results:
        return None
    arr = np.array(results)
    wins = arr[arr > 0]
    losses = arr[arr < 0]
    win_rate = len(wins) / len(arr)
    gross_win = wins.sum()
    gross_loss = -losses.sum()
    pf = gross_win / gross_loss if gross_loss else float("inf")
    # max losing streak
    streak = mx = 0
    for r in arr:
        streak = streak + 1 if r < 0 else 0
        mx = max(mx, streak)
    return {
        "trades": len(arr), "win_rate": win_rate,
        "total_R": arr.sum(), "avg_R": arr.mean(),
        "pf": pf, "max_loss_streak": mx,
    }


def main():
    ex = make_exchange()
    print(f"\n  BACKTEST — {C.BIAS_TF} bias / {C.ENTRY_TF} entry — {CANDLES} candles — STRONG>={C.STRONG_SCORE}/7, R:R=1:{C.ACCOUNT['target_rr']:.0f}\n")
    print(f"  {'SYMBOL':<12}{'TRADES':<8}{'WIN%':<8}{'TOT R':<9}{'AVG R':<9}{'PF':<7}{'MAXLOSS':<8}")
    print("  " + "-" * 60)

    all_results = []
    for sym in C.SYMBOLS:
        try:
            d4 = fetch(ex, sym, C.BIAS_TF, CANDLES)
            d15 = fetch(ex, sym, C.ENTRY_TF, CANDLES)
        except Exception as e:
            print(f"  ! {sym}: {e}"); continue

        bias4 = bias_series(d4).shift(1)  # use last fully-closed 4h bar
        # map 4h bias onto 15m bars (most recent known bias)
        bias_15m = pd.merge_asof(
            d15[["close"]].reset_index(),
            bias4.rename("bias").reset_index(),
            left_on="ts", right_on="ts", direction="backward",
        ).set_index("ts")["bias"].fillna(0)

        scores = entry_scores(d15)
        res = simulate(d15, bias_15m, scores)
        all_results.extend(res)
        s = stats(res)
        if s is None:
            print(f"  {sym:<12}{'0':<8}{'—':<8}"); continue
        pf = "inf" if s["pf"] == float("inf") else f"{s['pf']:.2f}"
        print(f"  {sym:<12}{s['trades']:<8}{s['win_rate']*100:<8.1f}{s['total_R']:<9.1f}{s['avg_R']:<9.2f}{pf:<7}{s['max_loss_streak']:<8}")

    agg = stats(all_results)
    print("  " + "-" * 60)
    if agg:
        pf = "inf" if agg["pf"] == float("inf") else f"{agg['pf']:.2f}"
        print(f"  {'ALL':<12}{agg['trades']:<8}{agg['win_rate']*100:<8.1f}{agg['total_R']:<9.1f}{agg['avg_R']:<9.2f}{pf:<7}{agg['max_loss_streak']:<8}")
        print(f"\n  Interpretation: avg R > 0 and PF > 1 => positive expectancy on this sample.")
        print(f"  With R:R 1:{C.ACCOUNT['target_rr']:.0f}, break-even win rate is "
              f"{100/(1+C.ACCOUNT['target_rr']):.1f}% — you need to beat that.\n")
    else:
        print("  No trades triggered. Loosen STRONG_SCORE in config.py or pull more candles.\n")


if __name__ == "__main__":
    main()
