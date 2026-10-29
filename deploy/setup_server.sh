#!/usr/bin/env bash
# Run this ON the cloud server (after you've copied the ecc-trading folder there).
# It installs Python + deps and sets up a service that keeps the alerter running
# 24/7 and auto-restarts on crash or reboot.
set -e

DIR="$(cd "$(dirname "$0")/.." && pwd)"
USER_NAME="$(whoami)"
echo "==> Installing alerter in $DIR (user: $USER_NAME)"

# --- Python + venv (works on Ubuntu/Debian and Oracle Linux/RHEL) ---
if command -v apt-get >/dev/null; then
  sudo apt-get update -y
  sudo apt-get install -y python3 python3-venv python3-pip
elif command -v dnf >/dev/null; then
  sudo dnf install -y python3 python3-pip
elif command -v yum >/dev/null; then
  sudo yum install -y python3 python3-pip
fi

cd "$DIR"
python3 -m venv .venv
./.venv/bin/pip install --upgrade pip
./.venv/bin/pip install -r requirements.txt

# --- systemd service ---
SERVICE=/etc/systemd/system/trading-alerts.service
sudo bash -c "cat > $SERVICE" <<EOF
[Unit]
Description=Crypto confluence Telegram alerter
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$USER_NAME
WorkingDirectory=$DIR
ExecStart=$DIR/.venv/bin/python $DIR/alerts.py --loop
Restart=always
RestartSec=30

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable trading-alerts
sudo systemctl restart trading-alerts

echo ""
echo "==> Done! The alerter now runs 24/7."
echo "    Status:  sudo systemctl status trading-alerts"
echo "    Logs:    journalctl -u trading-alerts -f"
echo "    Stop:    sudo systemctl stop trading-alerts"
