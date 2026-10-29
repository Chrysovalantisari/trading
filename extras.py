"""
Expert add-ons for alerts:
  1. volume confirmation + volume-profile POC
  2. funding rate (crowdedness)
  3. higher-timeframe (Daily) key levels + room check
  6. trade management plan (partial TP + move to breakeven)
"""
import pandas as pd

import indicators as ind
import context as ctx


# ---------------------------------------------------------------- 1. volume
def volume_context(df15):
    vol = df15["volume"]
    sig = vol.iloc[-2]
    avg = vol.iloc[-22:-2].mean()
    rv = sig / avg if avg else 0.0
    poc = ind.volume_poc(df15, lookback=120)
    price = df15["close"].iloc[-2]
    if rv >= 1.5:
        tag = "δυνατό breakout ✅"
    elif rv >= 1.0:
        tag = "ΟΚ"
    else:
        tag = "⚠️ χαμηλός — πιθανό fakeout"
    rel = "πάνω από POC ✅" if price > poc else "κάτω από POC"
    txt = f"📊 Volume: {rv:.1f}× μέσο — {tag}\n   POC {poc:.6g} (τιμή {rel})"
    return txt, rv


# ---------------------------------------------------------------- 2. funding
def funding_context(ex, symbol):
    from scanner import resolve_symbol
    try:
        fr = ex.fetch_funding_rate(resolve_symbol(ex, symbol))
        rate = fr.get("fundingRate")
    except Exception:
        return "💸 Funding: n/a", 0.0
    if rate is None:
        return "💸 Funding: n/a", 0.0
    pct = rate * 100
    if abs(pct) < 0.02:
        lab = "neutral ✅"
    elif pct > 0:
        lab = "longs πληρώνουν (crowded long)" + (" ⚠️" if pct >= 0.05 else "")
    else:
        lab = "shorts πληρώνουν (crowded short)" + (" ⚠️" if pct <= -0.05 else "")
    return f"💸 Funding: {pct:+.3f}% — {lab}", pct


# ---------------------------------------------------------------- 3. daily levels
def daily_levels(ex, symbol, entry, direction):
    from scanner import resolve_symbol
    try:
        o = ex.fetch_ohlcv(resolve_symbol(ex, symbol), "1d", limit=180)
    except Exception:
        return "🧱 Daily levels: n/a", True
    d = pd.DataFrame(o, columns=["ts", "open", "high", "low", "close", "volume"])
    sh = d["high"].values[ctx._pivots(d["high"], 2, "high")]
    sl = d["low"].values[ctx._pivots(d["low"], 2, "low")]
    res = sh[sh > entry]
    sup = sl[sl < entry]
    nearest_res = float(res.min()) if len(res) else None
    nearest_sup = float(sup.max()) if len(sup) else None

    lines = ["🧱 <b>Daily levels</b>:"]
    if nearest_res:
        lines.append(f"   resistance {nearest_res:.6g} ({(nearest_res/entry-1)*100:+.1f}%)")
    if nearest_sup:
        lines.append(f"   support {nearest_sup:.6g} ({(nearest_sup/entry-1)*100:+.1f}%)")

    room_ok = True
    if direction == 1 and nearest_res and (nearest_res / entry - 1) < 0.015:
        lines.append("   ⚠️ entry κολλητά σε daily resistance — λίγος χώρος για target")
        room_ok = False
    if direction == -1 and nearest_sup and (1 - nearest_sup / entry) < 0.015:
        lines.append("   ⚠️ entry κολλητά σε daily support — λίγος χώρος για target")
        room_ok = False
    return "\n".join(lines), room_ok


# ---------------------------------------------------------------- 6. trade plan
def trade_plan(lv, direction):
    entry, stop = lv["entry"], lv["stop"]
    risk = abs(entry - stop)
    if direction == 1:
        tp1 = entry + risk * 1.0
        tp2 = lv["target"]
    else:
        tp1 = entry - risk * 1.0
        tp2 = lv["target"]
    return (
        f"🧭 <b>Plan</b>:\n"
        f"   TP1 {tp1:.6g} (1R) → κλείσε 50%, μετά stop → breakeven ({entry:.6g})\n"
        f"   TP2 {tp2:.6g} (target) → άσε το υπόλοιπο με trailing stop"
    )
