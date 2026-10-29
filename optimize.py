"""
Grid-search optimizer. Loads cached history (run data.py first), computes base
indicators once per symbol, then sweeps decision parameters to find the
configuration with the best out-of-the-box expectancy across ALL symbols.

    python optimize.py

Ranks by average R per trade (expectancy), requiring a minimum number of trades
so a lucky 2-trade config can't win. Prints the top configs and the single best,
then tells you exactly what to put in config.py.

NOTE: this is in-sample optimization. A config that looks great here can still
fail live (overfitting). Treat the result as a hypothesis, then forward-test on
paper before risking money.
"""
import itertools
import sys

import config as C
import engine as E
from data import load_cached

# --- search space (decision params only; indicator periods stay fixed) ---
GRID = {
    "rr": [2.0, 3.0, 4.0, 5.0],
    "strong_score": [5, 6, 7],
    "adx_min": [15, 20, 25],
    "zone_lookback": [15, 20, 30],
    "green_streak": [2, 3],
}
MIN_TRADES = 40  # ignore configs that barely trade


def load_all():
    """Preload data + base indicators for every symbol. Returns list of dicts."""
    prepped = []
    for sym in C.SYMBOLS:
        d4 = load_cached(sym, C.BIAS_TF)
        d15 = load_cached(sym, C.ENTRY_TF)
        if d4 is None or d15 is None or len(d15) < 200:
            print(f"  ! {sym}: no cached data (run data.py)")
            continue
        b4 = E.base_indicators(d4, C.PARAMS)
        b15 = E.base_indicators(d15, C.PARAMS)
        prepped.append({"sym": sym, "d4": d4, "d15": d15, "b4": b4, "b15": b15})
    return prepped


def run_combo(prepped, rr, strong_score, adx_min, zone_lookback, green_streak):
    all_R = []
    for d in prepped:
        bias4 = E.bias_from_base(d["b4"], adx_min)
        bias15 = E.align_bias(bias4, d["d15"].index)
        ls, ss, zh, zl = E.scores_from_base(d["b15"], zone_lookback, green_streak, adx_min)
        res = E.simulate(d["b15"], bias15, ls, ss, zh, zl, rr, strong_score)
        if len(res):
            all_R.extend(res.tolist())
    return E.stats(all_R)


def main():
    print("\n  Loading cached data + base indicators...")
    prepped = load_all()
    if not prepped:
        sys.exit("  No data. Run:  python data.py")
    print(f"  {len(prepped)} symbols ready.\n")

    keys = list(GRID.keys())
    combos = list(itertools.product(*[GRID[k] for k in keys]))
    print(f"  Testing {len(combos)} configurations...\n")

    rows = []
    for combo in combos:
        params = dict(zip(keys, combo))
        s = run_combo(prepped, **params)
        if s and s["trades"] >= MIN_TRADES:
            rows.append((params, s))

    if not rows:
        sys.exit("  No config reached the minimum trade count. Lower MIN_TRADES or get more data.")

    # rank by expectancy (avg R), tie-break by profit factor
    rows.sort(key=lambda r: (r[1]["avg_R"], r[1]["pf"]), reverse=True)

    print(f"  {'RR':<5}{'STRG':<6}{'ADX':<5}{'ZONE':<6}{'STREAK':<8}"
          f"{'TRADES':<8}{'WIN%':<7}{'AVG R':<8}{'TOT R':<9}{'PF':<7}{'MAXL':<6}")
    print("  " + "-" * 82)
    for params, s in rows[:15]:
        pf = "inf" if s["pf"] == float("inf") else f"{s['pf']:.2f}"
        print(f"  {params['rr']:<5.0f}{params['strong_score']:<6}{params['adx_min']:<5}"
              f"{params['zone_lookback']:<6}{params['green_streak']:<8}"
              f"{s['trades']:<8}{s['win_rate']*100:<7.1f}{s['avg_R']:<8.2f}"
              f"{s['total_R']:<9.1f}{pf:<7}{s['max_loss_streak']:<6}")

    best_p, best_s = rows[0]
    print("\n  === BEST CONFIG (in-sample) ===")
    print(f"  expectancy {best_s['avg_R']:.2f} R/trade | win {best_s['win_rate']*100:.1f}% | "
          f"PF {best_s['pf']:.2f} | {best_s['trades']} trades | worst streak {best_s['max_loss_streak']}")
    verdict = "POSITIVE edge (in-sample)" if best_s["avg_R"] > 0.05 and best_s["pf"] > 1.2 else \
              "marginal / no reliable edge"
    print(f"  verdict: {verdict}")
    print("\n  To apply, set in config.py:")
    print(f"    ACCOUNT['target_rr'] = {best_p['rr']:.0f}")
    print(f"    STRONG_SCORE = {best_p['strong_score']}")
    print(f"    PARAMS['adx_min'] = {best_p['adx_min']}")
    print(f"    PARAMS['zone_lookback'] = {best_p['zone_lookback']}")
    print(f"    PARAMS['green_streak'] = {best_p['green_streak']}")
    print("\n  Reminder: in-sample winner != live winner. Forward-test on paper next.\n")


if __name__ == "__main__":
    main()
