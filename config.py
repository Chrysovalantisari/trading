"""
Configuration for the confluence scanner.
Edit this file to change instruments, timeframes, thresholds and risk settings.
"""

# --- Account / risk profile (from your answers) ---
ACCOUNT = {
    "capital": 3500.0,          # your working capital (2-5k -> midpoint)
    "risk_pct_per_trade": 0.02, # 1-3% -> default 2%
    "target_rr": 4.0,           # validated out-of-sample (was 7; 1:4 held up best)
    "max_leverage_allowed": 100,
    "leverage_safety_buffer": 1.5,  # keep liquidation this x further than the stop
}

# --- Exchange for public OHLCV (no API key needed) ---
EXCHANGE = "binance"
MARKET_TYPE = "future"  # perp futures universe (matches leverage trading)

# --- Watchlist (major liquid crypto perps; edit freely) ---
SYMBOLS = [
    "BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT",
    "DOGE/USDT", "AVAX/USDT", "LINK/USDT", "TON/USDT", "ADA/USDT",
    "SUI/USDT", "NEAR/USDT",
]

# --- Timeframes: higher = bias, lower = entry trigger ---
BIAS_TF = "4h"
ENTRY_TF = "15m"
CANDLES = 300  # history pulled per timeframe

# --- Strategy parameters ---
PARAMS = {
    "zone_lookback": 30,      # validated (was 20)
    "green_streak": 3,        # validated: 3 consecutive candles beat 2
    "rsi_period": 14,
    "adx_period": 14,
    "adx_min": 25,            # validated: only trade STRONG trends (was 20)
    "atr_period": 14,
    "hma_period": 21,
    "st_period": 10,
    "st_mult": 3.0,
    "kc_period": 20,
    "kc_mult": 2.0,
}

# A setup needs this many confirmations (out of 7) to be labelled STRONG
STRONG_SCORE = 5   # validated out-of-sample
BUY_SCORE = 4
