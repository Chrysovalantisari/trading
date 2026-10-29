"""
Historical data downloader with pagination + local CSV cache.

Binance returns max ~1500 candles per call, so we page backwards with `since`
until we have the requested history, then cache to data/<symbol>_<tf>.csv.

    python data.py            # download default history for all SYMBOLS
    python data.py 12         # 12 months of history
"""
import os
import sys
import time
import pandas as pd

import config as C

try:
    import ccxt
except ImportError:
    sys.exit("ccxt not installed. Run ./run.sh first.")

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
os.makedirs(DATA_DIR, exist_ok=True)

DEFAULT_MONTHS = 8


def make_exchange():
    return getattr(ccxt, C.EXCHANGE)({
        "enableRateLimit": True,
        "options": {"defaultType": C.MARKET_TYPE},
    })


def cache_path(symbol, timeframe):
    safe = symbol.replace("/", "-")
    return os.path.join(DATA_DIR, f"{safe}_{timeframe}.csv")


def fetch_history(ex, symbol, timeframe, months):
    tf_ms = ex.parse_timeframe(timeframe) * 1000
    now = ex.milliseconds()
    since = now - int(months * 30 * 24 * 3600 * 1000)
    rows = []
    while since < now:
        batch = ex.fetch_ohlcv(symbol, timeframe, since=since, limit=1500)
        if not batch:
            break
        rows += batch
        last_ts = batch[-1][0]
        if last_ts + tf_ms <= since:  # no forward progress -> stop
            break
        since = last_ts + tf_ms
        time.sleep(ex.rateLimit / 1000)
    df = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close", "volume"])
    df = df.drop_duplicates("ts").sort_values("ts")
    df["ts"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    return df.set_index("ts")


def load_or_fetch(ex, symbol, timeframe, months=DEFAULT_MONTHS, refresh=False):
    path = cache_path(symbol, timeframe)
    if os.path.exists(path) and not refresh:
        df = pd.read_csv(path, index_col="ts", parse_dates=["ts"])
        return df
    df = fetch_history(ex, symbol, timeframe, months)
    df.to_csv(path)
    return df


def load_cached(symbol, timeframe):
    """Read-only loader used by the optimizer (no network)."""
    path = cache_path(symbol, timeframe)
    if not os.path.exists(path):
        return None
    return pd.read_csv(path, index_col="ts", parse_dates=["ts"])


def main():
    months = float(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_MONTHS
    ex = make_exchange()
    print(f"\n  Downloading ~{months:g} months of history to {DATA_DIR}\n")
    for sym in C.SYMBOLS:
        for tf in (C.BIAS_TF, C.ENTRY_TF):
            try:
                df = load_or_fetch(ex, sym, tf, months, refresh=True)
                print(f"  {sym:<12} {tf:<5} {len(df):>7} candles  "
                      f"[{df.index[0]:%Y-%m-%d} -> {df.index[-1]:%Y-%m-%d}]")
            except Exception as e:
                print(f"  ! {sym} {tf}: {e}")
    print("\n  Done. Now run:  python optimize.py\n")


if __name__ == "__main__":
    main()
