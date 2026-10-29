"""
Out-of-sample validation — the honest test.

Splits each symbol's 15m history into TRAIN (first 60%) and TEST (last 40%).
It optimizes the grid ONLY on TRAIN, picks the best config, then measures that
exact config on TEST data it never saw. If the edge survives on TEST, it is
credible. If it collapses, the in-sample result was overfitting.

    python validate.py
"""
import itertools
import sys

import config as C
import engine as E
from data import load_cached
from optimize import GRID, MIN_TRADES

SPLIT = 0.60
# round-trip cost %, override from CLI: python validate.py 0.04  (limit/maker orders)
COST_PCT = float(sys.argv[1]) if len(sys.argv) > 1 else 0.11


def prep():
    out = []
    for sym in C.SYMBOLS:
        d4 = load_cached(sym, C.BIAS_TF)
        d15 = load_cached(sym, C.ENTRY_TF)
        if d4 is None or d15 is None or len(d15) < 500:
            continue
        b4 = E.base_indicators(d4, C.PARAMS)
        b15 = E.base_indicators(d15, C.PARAMS)
        out.append({
            "sym": sym, "d15": d15, "b15": b15,
            "b4": b4, "cut": int(len(d15) * SPLIT),
        })
    return out


def eval_combo(prepped, params, window, cost_pct=0.0):
    """window = 'train' or 'test'. Aggregates R across symbols."""
    all_R = []
    for d in prepped:
        bias4 = E.bias_from_base(d["b4"], params["adx_min"])
        bias15 = E.align_bias(bias4, d["d15"].index)
        ls, ss, zh, zl = E.scores_from_base(
            d["b15"], params["zone_lookback"], params["green_streak"], params["adx_min"])
        if window == "train":
            start, stop = None, d["cut"]
        else:
            start, stop = d["cut"], None
        res = E.simulate(d["b15"], bias15, ls, ss, zh, zl,
                         params["rr"], params["strong_score"],
                         start=start, stop=stop, cost_pct=cost_pct)
        if len(res):
            all_R.extend(res.tolist())
    return E.stats(all_R)


def main():
    print("\n  Out-of-sample validation (train 60% / test 40%)\n")
    prepped = prep()
    if not prepped:
        sys.exit("  No cached data. Run:  python data.py")

    keys = list(GRID.keys())
    combos = [dict(zip(keys, c)) for c in itertools.product(*[GRID[k] for k in keys])]
    print(f"  Optimizing {len(combos)} configs on TRAIN...")

    scored = []
    for p in combos:
        s = eval_combo(prepped, p, "train")
        if s and s["trades"] >= int(MIN_TRADES * SPLIT):
            scored.append((p, s))
    if not scored:
        sys.exit("  No config qualified on train.")
    scored.sort(key=lambda r: (r[1]["avg_R"], r[1]["pf"]), reverse=True)
    best_p, train_s = scored[0]

    test_s = eval_combo(prepped, best_p, "test")
    test_c = eval_combo(prepped, best_p, "test", cost_pct=COST_PCT)

    print(f"\n  Winner on TRAIN: RR={best_p['rr']:.0f} STRONG={best_p['strong_score']} "
          f"ADX={best_p['adx_min']} ZONE={best_p['zone_lookback']} STREAK={best_p['green_streak']}\n")
    print(f"  {'':<14}{'TRADES':<8}{'WIN%':<8}{'AVG R':<8}{'TOT R':<9}{'PF':<7}{'MAXL':<6}")
    print("  " + "-" * 56)
    for lbl, s in [("TRAIN", train_s), ("TEST", test_s), (f"TEST+COSTS", test_c)]:
        if s is None:
            print(f"  {lbl:<14}{'0':<8}no trades"); continue
        pf = "inf" if s["pf"] == float("inf") else f"{s['pf']:.2f}"
        print(f"  {lbl:<14}{s['trades']:<8}{s['win_rate']*100:<8.1f}"
              f"{s['avg_R']:<8.2f}{s['total_R']:<9.1f}{pf:<7}{s['max_loss_streak']:<6}")

    print(f"\n  (costs = {COST_PCT:.2f}% round-trip fees+slippage per trade)")
    print("\n  === VERDICT (after costs) ===")
    final = test_c
    if final and final["avg_R"] > 0.05 and final["pf"] > 1.15:
        print("  ✅ Edge SURVIVES fees out-of-sample. Credible — paper-trade it next.")
    elif final and final["avg_R"] > 0:
        print("  🟡 Thin positive edge after costs. Real but fragile — paper-trade, keep costs low (limit/maker orders).")
    else:
        print("  ❌ Fees KILL the edge. Not tradeable as-is — needs bigger R:R wins or fewer/better trades.")
    print("\n  Next: forward/paper-trade before real money. And NEVER 100x — the "
          f"worst losing streak here ({test_c['max_loss_streak'] if test_c else '?'}) would liquidate you.\n")


if __name__ == "__main__":
    main()
