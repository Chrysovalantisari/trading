"""
Two-stage Telegram alerter.

  WATCH    -> bias aligned, confluence building, price near the trigger zone.
              "Arm a LIMIT order at X" — you set it and walk away.
  CONFIRMED-> full STRONG setup fired (zone broken + confluence >= STRONG_SCORE).

It de-duplicates: an alert is sent only when a symbol's state CHANGES, so you are
not spammed every run. State is kept in alerts_state.json.

Run once (for cron / manual):   python alerts.py
Run continuously:               python alerts.py --loop
"""
import json
import os
import sys
import time
from datetime import datetime, timezone

import config as C
import notify
import context as ctx
import extras
import news as newsmod
from scanner import make_exchange, fetch, bias_from_tf, entry_signal, risk_block

STATE_PATH = os.path.join(os.path.dirname(__file__), "alerts_state.json")
WATCH_NEAR_PCT = 0.006   # within 0.6% of the trigger = "approaching"
LOOP_SECONDS = 15 * 60   # re-scan every 15m candle


def load_state():
    if os.path.exists(STATE_PATH):
        return json.load(open(STATE_PATH))
    return {}


def save_state(s):
    json.dump(s, open(STATE_PATH, "w"), indent=2)


def analyze(ex, sym, news_text="", danger=False):
    """Return (state_key, message or None) for a symbol."""
    df_bias = fetch(ex, sym, C.BIAS_TF, C.CANDLES)
    df_entry = fetch(ex, sym, C.ENTRY_TF, C.CANDLES)
    bias = bias_from_tf(df_bias)
    if bias == 0:
        return "none", None

    score, checks, lv = entry_signal(df_entry, bias)
    side = "BUY" if bias == 1 else "SELL"
    emoji = "🟢" if bias == 1 else "🔴"
    risk = risk_block(lv, bias)
    near = abs(lv["entry"] - lv["trigger_level"]) / lv["entry"] < WATCH_NEAR_PCT

    is_confirmed = score >= C.STRONG_SCORE and checks["zone_break"]
    is_watch = score >= C.STRONG_SCORE - 1 and near
    if not (is_confirmed or is_watch):
        return "none", None

    # expert add-ons (fetched only when a setup actually qualifies)
    vol_text, _ = extras.volume_context(df_entry)
    fund_text, _ = extras.funding_context(ex, sym)
    daily_text, room_ok = extras.daily_levels(ex, sym, lv["entry"], bias)
    plan_text = extras.trade_plan(lv, bias)
    quality = []
    if danger:
        quality.append("⛔ High-impact news κοντά")
    if not room_ok:
        quality.append("⚠️ λίγος χώρος σε daily level")
    quality_line = ("\n<b>" + " · ".join(quality) + "</b>") if quality else ""

    if is_confirmed:
        key = f"CONFIRMED_{side}"
        ctx_text, _, _ = ctx.mtf_context_block(df_bias, df_entry, bias)
        msg = (
            f"{emoji} <b>STRONG {side}</b> — <b>{sym}</b>\n"
            f"Confluence {score}/7 · ADX {lv['adx']:.0f} · RSI {lv['rsi']:.0f}{quality_line}\n\n"
            f"{ctx_text}\n\n"
            f"{vol_text}\n{fund_text}\n{daily_text}\n\n"
            f"Entry ~<b>{lv['entry']:.6g}</b>\n"
            f"Stop <b>{lv['stop']:.6g}</b> ({risk['stop_pct']*100:.2f}%)\n"
            f"Target <b>{lv['target']:.6g}</b>  (R:R 1:{C.ACCOUNT['target_rr']:.0f})\n"
            f"Size <b>{risk['qty']:.4g}</b> units (~${risk['notional']:.0f})\n"
            f"⚠️ Max safe leverage: <b>{risk['max_safe_lev']}x</b>\n\n"
            f"{plan_text}\n\n"
            f"{news_text}\n\n"
            f"➡️ <b>LIMIT {side}</b> near entry (limit = maker fees = keeps the edge)."
        )
        return key, msg

    key = f"WATCH_{side}"
    ctx_text, must_break, _ = ctx.mtf_context_block(df_bias, df_entry, bias)
    msg = (
        f"👀 <b>WATCH {side}</b> — <b>{sym}</b> (building: {score}/7, ADX {lv['adx']:.0f}){quality_line}\n"
        f"Approaching a STRONG {side}.\n\n"
        f"{ctx_text}\n\n"
        f"{vol_text}\n{fund_text}\n{daily_text}\n\n"
        f"➡️ <b>Arm LIMIT {side} @ {must_break:.6g}</b> (break level)\n"
        f"If it triggers: stop ~{lv['stop']:.6g}, target ~{lv['target']:.6g}, max lev {risk['max_safe_lev']}x.\n\n"
        f"{plan_text}\n\n"
        f"{news_text}\n\n"
        f"Set it and walk away — fills automatically if the level breaks."
    )
    return key, msg


def scan_once(ex, state, announce=False):
    sent = 0
    news_text, danger = newsmod.news_block()  # fetched once per scan
    for sym in C.SYMBOLS:
        try:
            key, msg = analyze(ex, sym, news_text, danger)
        except Exception as e:
            print(f"  ! {sym}: {e}")
            continue
        prev = state.get(sym, "none")
        if key != prev:
            if msg:
                notify.send(msg)
                sent += 1
                print(f"  -> alert sent: {sym} {key}")
            state[sym] = key
    save_state(state)
    stamp = datetime.now(timezone.utc).strftime("%H:%M UTC")
    print(f"  scan done {stamp} — {sent} new alert(s)")
    if announce and sent == 0:
        pass
    return sent


def main():
    loop = "--loop" in sys.argv
    ex = make_exchange()
    state = load_state()
    print("  Alerter started" + (" (loop mode)" if loop else " (single scan)"))
    if loop:
        notify.send("🟢 Alerter is live — scanning every 15m. You'll get WATCH + CONFIRMED signals.")
        while True:
            scan_once(ex, state)
            time.sleep(LOOP_SECONDS)
    else:
        scan_once(ex, state)


if __name__ == "__main__":
    main()
