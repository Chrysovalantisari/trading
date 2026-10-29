"""
Telegram notifier. Reads TELEGRAM_TOKEN / TELEGRAM_CHAT_ID from .env and sends
messages. No external deps beyond requests (already installed via ccxt).
"""
import os
import requests

ENV_PATH = os.path.join(os.path.dirname(__file__), ".env")


def load_env():
    """Credentials from .env (local) or environment variables (CI/GitHub Secrets).
    Environment variables win, so GitHub Actions works with no .env file."""
    creds = {}
    if os.path.exists(ENV_PATH):
        for line in open(ENV_PATH):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                creds[k.strip()] = v.strip()
    for key in ("TELEGRAM_TOKEN", "TELEGRAM_CHAT_ID"):
        if os.environ.get(key):
            creds[key] = os.environ[key]
    return creds


def send(text, disable_preview=True):
    c = load_env()
    token = c.get("TELEGRAM_TOKEN")
    chat_id = c.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        raise RuntimeError("Missing TELEGRAM_TOKEN / TELEGRAM_CHAT_ID in .env")
    r = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": disable_preview,
        },
        timeout=15,
    )
    r.raise_for_status()
    return r.json()


if __name__ == "__main__":
    import sys
    msg = " ".join(sys.argv[1:]) or "✅ Test from your trading alerter — it works!"
    print(send(msg))
