"""
Confluence scanner — implements YOUR setup:

  STRONG BUY  = 4h bias bullish  AND on 15m: price breaks the recent major zone
                + a streak of green candles + indicator confirmations.
  STRONG SELL = the mirror image (bearish bias + breakdown + red streak + confirmations).

It does NOT predict the future. It scans the market and ranks the setups where the
most of your own criteria line up at the same time, plus the risk/position/leverage math.

Run:  python scanner.py
"""
import sys
from datetime import datetime, timezone

import pandas as pd

import config as C
import indicators as ind

try:
    import ccxt
except ImportError:
    sys.exit("ccxt not installed. Run ./run.sh (it creates a venv and installs deps).")


# ---------------------------------------------------------------- data
def resolve_symbol(ex, base):
    """Map a base pair like 'BTC/USDT' to the exchange's market id.
    Perp exchanges use the unified swap form 'BTC/USDT:USDT'."""
    if base in ex.markets:
        return base
    alt = base + ":USDT"
    if alt in ex.markets:
        return alt
    return base


def make_exchange():
    """Try LIVE_EXCHANGES in order; return the first that actually responds
    (Binance is geo-blocked from US cloud, so we fall through to others)."""
    exchanges = getattr(C, "LIVE_EXCHANGES", [C.EXCHANGE])
    last_err = None
    for exid in exchanges:
        try:
            dtype = "future" if exid == "binance" else "swap"
            ex = getattr(ccxt, exid)({
                "enableRateLimit": True,
                "options": {"defaultType": dtype},
            })
            ex.load_markets()
            # probe: must be able to pull candles from this location
            ex.fetch_ohlcv(resolve_symbol(ex, C.SYMBOLS[0]), "15m", limit=2)
            ex.chosen_id = exid
            return ex
        except Exception as e:
            last_err = e
            continue
    raise RuntimeError(f"No reachable exchange. Last error: {last_err}")


def fetch(ex, symbol, timeframe, limit):
    o = ex.fetch_ohlcv(resolve_symbol(ex, symbol), timeframe=timeframe, limit=limit)
    df = pd.DataFrame(o, columns=["ts", "open", "high", "low", "close", "volume"])
    df["ts"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    return df.set_index("ts")


# ---------------------------------------------------------------- analysis
def bias_from_tf(df):
    """Higher-timeframe trend bias: +1 bullish, -1 bearish, 0 neutral."""
    p = C.PARAMS
    ich = ind.ichimoku(df)
    st, st_dir = ind.supertrend(df, p["st_period"], p["st_mult"])
    hma = ind.hma(df["close"], p["hma_period"])
    plus_di, minus_di, adx = ind.dmi_adx(df, p["adx_period"])

    last = -2  # last CLOSED candle
    c = df["close"].iloc[last]
    above_cloud = c > ich["cloud_top"].iloc[last]
    below_cloud = c < ich["cloud_bottom"].iloc[last]
    hma_rising = hma.iloc[last] > hma.iloc[last - 3]
    strong = adx.iloc[last] >= p["adx_min"]

    bull = above_cloud and st_dir.iloc[last] == 1 and hma_rising and strong and plus_di.iloc[last] > minus_di.iloc[last]
    bear = below_cloud and st_dir.iloc[last] == -1 and (not hma_rising) and strong and minus_di.iloc[last] > plus_di.iloc[last]
    return 1 if bull else (-1 if bear else 0)


def entry_signal(df, direction):
    """Score the 15m trigger for the given direction (+1 long / -1 short).
    Returns (score, checks dict, levels dict)."""
    p = C.PARAMS
    close = df["close"]
    last = -2  # last closed candle
    c = close.iloc[last]

    # major zone from recent swing high/low (excludes the breakout candle itself)
    zone_high = df["high"].iloc[last - p["zone_lookback"]:last].max()
    zone_low = df["low"].iloc[last - p["zone_lookback"]:last].min()

    rsi = ind.rsi(close, p["rsi_period"])
    macd_line, signal_line, hist = ind.macd(close)
    st, st_dir = ind.supertrend(df, p["st_period"], p["st_mult"])
    hma = ind.hma(close, p["hma_period"])
    plus_di, minus_di, adx = ind.dmi_adx(df, p["adx_period"])
    kc_up, kc_mid, kc_low = ind.keltner(df, p["kc_period"], p["kc_mult"])
    atr = ind.atr(df, p["atr_period"]).iloc[last]

    # green/red candle continuation streak
    body = df["close"] - df["open"]
    bull_streak = all(body.iloc[last - i] > 0 for i in range(p["green_streak"]))
    bear_streak = all(body.iloc[last - i] < 0 for i in range(p["green_streak"]))

    if direction == 1:
        checks = {
            "zone_break":   c > zone_high,
            "candle_streak": bull_streak,
            "supertrend":   st_dir.iloc[last] == 1,
            "hma":          c > hma.iloc[last] and hma.iloc[last] > hma.iloc[last - 2],
            "macd":         macd_line.iloc[last] > signal_line.iloc[last],
            "rsi":          50 < rsi.iloc[last] < 75,
            "dmi":          plus_di.iloc[last] > minus_di.iloc[last] and adx.iloc[last] >= p["adx_min"],
        }
        kc_momentum = c > kc_mid.iloc[last]
        entry = c
        stop = min(zone_high, c) - 1.5 * atr
        target = entry + (entry - stop) * C.ACCOUNT["target_rr"]
        trigger_level = zone_high
    else:
        checks = {
            "zone_break":   c < zone_low,
            "candle_streak": bear_streak,
            "supertrend":   st_dir.iloc[last] == -1,
            "hma":          c < hma.iloc[last] and hma.iloc[last] < hma.iloc[last - 2],
            "macd":         macd_line.iloc[last] < signal_line.iloc[last],
            "rsi":          25 < rsi.iloc[last] < 50,
            "dmi":          minus_di.iloc[last] > plus_di.iloc[last] and adx.iloc[last] >= p["adx_min"],
        }
        kc_momentum = c < kc_mid.iloc[last]
        entry = c
        stop = max(zone_low, c) + 1.5 * atr
        target = entry - (stop - entry) * C.ACCOUNT["target_rr"]
        trigger_level = zone_low

    score = sum(1 for v in checks.values() if v)
    if kc_momentum:
        score += 0  # KC used as tiebreaker info only, not a core vote
    levels = {
        "entry": entry, "stop": stop, "target": target,
        "trigger_level": trigger_level, "atr": atr,
        "rsi": rsi.iloc[last], "adx": adx.iloc[last],
    }
    return score, checks, levels


def risk_block(levels, direction):
    acc = C.ACCOUNT
    entry, stop = levels["entry"], levels["stop"]
    stop_dist = abs(entry - stop)
    stop_pct = stop_dist / entry
    risk_amount = acc["capital"] * acc["risk_pct_per_trade"]
    qty = risk_amount / stop_dist if stop_dist else 0
    notional = qty * entry
    # leverage at which liquidation (~1/lev) sits safely beyond the stop
    max_safe_lev = int(1 / (stop_pct * acc["leverage_safety_buffer"])) if stop_pct else 0
    max_safe_lev = max(1, min(max_safe_lev, acc["max_leverage_allowed"]))
    return {
        "stop_pct": stop_pct,
        "risk_amount": risk_amount,
        "qty": qty,
        "notional": notional,
        "max_safe_lev": max_safe_lev,
    }


def label(score):
    if score >= C.STRONG_SCORE:
        return "STRONG"
    if score >= C.BUY_SCORE:
        return "SETUP"
    return None


# ---------------------------------------------------------------- main
def main():
    ex = make_exchange()
    print(f"\n  Confluence scan — {datetime.now(timezone.utc):%Y-%m-%d %H:%M UTC}")
    print(f"  bias={C.BIAS_TF}  entry={C.ENTRY_TF}  capital=${C.ACCOUNT['capital']:.0f}  risk={C.ACCOUNT['risk_pct_per_trade']*100:.0f}%/trade\n")

    rows = []
    for sym in C.SYMBOLS:
        try:
            df_bias = fetch(ex, sym, C.BIAS_TF, C.CANDLES)
            df_entry = fetch(ex, sym, C.ENTRY_TF, C.CANDLES)
        except Exception as e:
            print(f"  ! {sym}: {e}")
            continue

        bias = bias_from_tf(df_bias)
        if bias == 0:
            rows.append((sym, "—", "no bias", 0, None, None))
            continue

        score, checks, levels = entry_signal(df_entry, bias)
        lab = label(score)
        side = "LONG" if bias == 1 else "SHORT"
        tag = (f"STRONG {('BUY' if bias==1 else 'SELL')}" if lab == "STRONG"
               else (f"{side} setup" if lab == "SETUP" else f"{side} watch"))
        risk = risk_block(levels, bias) if lab else None
        rows.append((sym, side, tag, score, levels, risk))

    # rank: strong first, then by score
    rows.sort(key=lambda r: (-(r[3]), r[0]))

    print(f"  {'SYMBOL':<12}{'SIDE':<7}{'SIGNAL':<16}{'SCORE':<7}{'ENTRY':<12}{'STOP':<12}{'TARGET':<12}{'SAFE LEV':<9}")
    print("  " + "-" * 94)
    for sym, side, tag, score, levels, risk in rows:
        if levels is None:
            print(f"  {sym:<12}{side:<7}{tag:<16}{score:<7}")
            continue
        safe = f"{risk['max_safe_lev']}x" if risk else "-"
        print(f"  {sym:<12}{side:<7}{tag:<16}{score}/7    "
              f"{levels['entry']:<12.4g}{levels['stop']:<12.4g}{levels['target']:<12.4g}{safe:<9}")

    # detail on the strong setups
    strong = [r for r in rows if r[2].startswith("STRONG")]
    if strong:
        print("\n  === STRONG SETUPS (your criteria all lined up) ===")
        for sym, side, tag, score, levels, risk in strong:
            print(f"\n  {sym}  {tag}  (score {score}/7)")
            print(f"    entry ~{levels['entry']:.4g} | stop {levels['stop']:.4g} "
                  f"({risk['stop_pct']*100:.2f}% away) | target {levels['target']:.4g}")
            print(f"    alert trigger level: {levels['trigger_level']:.4g}  "
                  f"(set a price alert here)")
            print(f"    RSI {levels['rsi']:.0f} | ADX {levels['adx']:.0f}")
            print(f"    risk ${risk['risk_amount']:.0f} -> size {risk['qty']:.4g} "
                  f"units (${risk['notional']:.0f} notional)")
            print(f"    >>> MAX SAFE LEVERAGE for this stop: {risk['max_safe_lev']}x  "
                  f"(using {C.ACCOUNT['max_leverage_allowed']}x would likely liquidate before your stop!)")
    else:
        print("\n  No STRONG setup right now. Patience is a position.")
    print()


if __name__ == "__main__":
    main()
