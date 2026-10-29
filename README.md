# Confluence Trading Scanner

A market scanner that finds setups where **your own criteria line up at once** —
a 4h trend bias plus a 15m "break a major zone + green-candle continuation
confirmed by indicators" trigger — and does the risk/leverage math for you.

It is an **analysis & education tool. It does not predict prices and does not give
guaranteed buy/sell signals.** Trading leveraged crypto can lose 100% of your money
(and more with leverage). You own every decision and every risk.

## Quick start
```bash
cd ~/ecc-trading
chmod +x run.sh
./run.sh
```
`run.sh` builds a local Python venv, installs `ccxt/pandas/numpy`, and runs the scan
on public Binance futures data (no API key needed).

Or manually:
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python scanner.py
```

## What you get
- A ranked watchlist: SIDE, SIGNAL (STRONG BUY/SELL · setup · watch), confluence score /7,
  entry, stop, target, and **max safe leverage**.
- Detail on STRONG setups: the exact **price level to set an alert on**, RSI/ADX,
  position size for your risk %, and a loud warning when 100x would liquidate you
  before your stop.

## Files
| file | purpose |
|---|---|
| `config.py` | instruments, timeframes, thresholds, your capital/risk |
| `indicators.py` | RSI, DMI/ADX, ATR, MACD, Ichimoku, Supertrend, Keltner, HMA (pure pandas) |
| `scanner.py` | multi-timeframe confluence logic + risk engine |
| `STRATEGY.md` | the exact rules, from your profile |

## Next steps (ask me)
- Backtest the rules on history to see the real win rate before trusting them.
- Price alerts / Telegram notifications when a STRONG setup appears.
- Add volume-profile value-area filter, or stocks/forex via another data source.

> Not financial advice.
