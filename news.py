"""
Economic calendar — upcoming HIGH-impact events, shown in Cyprus time.
Source: faireconomy (ForexFactory weekly JSON). For crypto the market-movers are
mostly USD events (FOMC, CPI, NFP, PCE) but we keep all High-impact entries.
"""
import datetime
import json
import os
import time

import requests

try:
    from zoneinfo import ZoneInfo
    CY = ZoneInfo("Asia/Nicosia")
except Exception:  # pragma: no cover
    CY = datetime.timezone(datetime.timedelta(hours=2))  # EET fallback

FEED = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
# Same economic events investing.com lists. We keep ONLY High-impact (major)
# releases from major economies. USD moves crypto most, so it's prioritised.
MAJOR_COUNTRIES = {"USD", "EUR", "GBP", "JPY", "CNY"}

CACHE_PATH = os.path.join(os.path.dirname(__file__), "news_cache.json")
CACHE_TTL = 3600  # refetch at most once per hour (the feed rate-limits)


def fetch_events():
    """Return calendar events, caching to disk to avoid rate limits.
    Falls back to stale cache if the network/feed fails."""
    if os.path.exists(CACHE_PATH):
        age = time.time() - os.path.getmtime(CACHE_PATH)
        if age < CACHE_TTL:
            return json.load(open(CACHE_PATH))
    try:
        r = requests.get(FEED, timeout=20, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36",
            "Accept": "application/json",
        })
        r.raise_for_status()
        data = r.json()
        json.dump(data, open(CACHE_PATH, "w"))
        return data
    except Exception:
        if os.path.exists(CACHE_PATH):
            return json.load(open(CACHE_PATH))  # stale but better than nothing
        raise


def upcoming_high_impact(within_hours=24, now=None, relevant=MAJOR_COUNTRIES):
    now = now or datetime.datetime.now(datetime.timezone.utc)
    out = []
    for e in fetch_events():
        if e.get("impact") != "High":
            continue
        if relevant and e.get("country") not in relevant:
            continue
        try:
            dt = datetime.datetime.fromisoformat(e["date"])
        except Exception:
            continue
        dt_utc = dt.astimezone(datetime.timezone.utc)
        hrs = (dt_utc - now).total_seconds() / 3600
        if 0 <= hrs <= within_hours:
            out.append({
                "title": e["title"],
                "country": e.get("country", ""),
                "cy": dt_utc.astimezone(CY),
                "hours": hrs,
            })
    out.sort(key=lambda x: x["hours"])
    return out


def news_block(within_hours=24, danger_hours=2):
    """Return (text, danger_flag). danger_flag=True if a high-impact event is
    within danger_hours -> do not open new positions."""
    try:
        evs = upcoming_high_impact(within_hours)
    except Exception:
        return "📅 News: δεν φορτώθηκε το calendar", False
    if not evs:
        return "📅 News: κανένα high-impact (USD/EUR) στο επόμενο 24ωρο ✅", False
    danger = any(e["hours"] <= danger_hours for e in evs)
    lines = ["📅 <b>Upcoming high-impact</b> (ώρα Κύπρου):"]
    for e in evs[:4]:
        flag = "⛔" if e["hours"] <= danger_hours else "•"
        lines.append(f"   {flag} {e['cy']:%a %H:%M} {e['country']} {e['title']} (σε {e['hours']:.1f}h)")
    if danger:
        lines.append("   ⛔ <b>Event πολύ κοντά — ΜΗΝ ανοίξεις θέση τώρα</b>")
    return "\n".join(lines), danger


if __name__ == "__main__":
    txt, danger = news_block()
    print(txt)
    print("DANGER" if danger else "clear")
