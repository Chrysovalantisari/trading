# Strategy Spec

Built from your trading profile. This is the exact logic the scanner enforces.

## Your profile
| | |
|---|---|
| Capital | 2–5k (default 3.5k in `config.py`) |
| Style | day trading + swing |
| Markets | crypto perps (because of 100x leverage) |
| Direction | long + short |
| Risk / trade | 1–3% (default 2%) |
| Target R:R | 1:5 to 1:10 (default 1:7) |
| Bias timeframe | 4h |
| Entry timeframe | 15m |
| Indicators | RSI, DMI/ADX, ATR, MACD, Ichimoku, Supertrend, Keltner, HMA |
| Volume | volume profile (POC) only |
| News | major macro events + technical |

## Your definition of a strong entry (encoded)
> "Break a major zone + continuation of green candles, confirmed by indicators."

### STRONG BUY requires ALL of:
1. **4h bias bullish** — price above Ichimoku cloud, Supertrend up, HMA rising, ADX ≥ 20, +DI > −DI.
2. **15m trigger** scoring ≥ 6/7 confirmations:
   - price breaks the recent major zone (20-bar swing high)
   - ≥ 2 consecutive green candles (continuation)
   - Supertrend up · HMA rising & price above it · MACD > signal · RSI 50–75 · +DI > −DI with ADX ≥ 20

STRONG SELL is the exact mirror (bearish bias + breakdown + red continuation).

Scores 4–5/7 are labelled **setup/watch**, not strong.

## Risk & position sizing (automatic)
- Stop = zone edge ∓ 1.5 × ATR(15m).
- Size so that hitting the stop loses only your `risk_pct_per_trade`.
- Target = R:R × stop distance.
- **Max safe leverage** = computed so liquidation sits 1.5× further than your stop.
  This is the single most important number on screen for you.

## ⚠️ The 100x reality
At 100x, liquidation is ~1% from entry. Your stops are usually further than 1%,
so 100x would liquidate you **before** the stop triggers. The scanner prints the
max leverage that keeps your stop inside the liquidation band — respect it.

## Tuning
Edit `config.py`: `SYMBOLS`, `BIAS_TF`/`ENTRY_TF`, `STRONG_SCORE`, risk settings.
