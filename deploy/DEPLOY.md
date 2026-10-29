# 24/7 Cloud Deployment — Oracle Cloud Always-Free

Goal: run the alerter on a free cloud server so you get Telegram alerts even with
your laptop closed / off / no internet. You only need Telegram on your phone.

Everything server-side is automated by `setup_server.sh`. You do the account +
VM creation (one time), then copy the folder up and run one script.

---

## Part A — Create the free server (one time, ~15 min)

1. Go to **https://www.oracle.com/cloud/free/** → **Start for free**.
2. Sign up. It asks for a card for identity verification — **Always-Free is never charged**.
   Pick a home region close to you (e.g. Frankfurt / Zurich).
3. In the console: **Menu → Compute → Instances → Create Instance**.
   - Name: `trading-alerter`
   - Image: **Canonical Ubuntu** (22.04 or newer)
   - Shape: keep an **Always-Free-eligible** shape (e.g. `VM.Standard.E2.1.Micro`,
     or an Ampere `A1.Flex` with 1 OCPU / 6 GB — both are free).
   - **SSH keys:** choose **Generate a key pair for me** → **Download the private key**
     (a `.key` file). Keep it safe — it's your password to the server.
   - Click **Create**. Wait until it's **Running**, then copy the **Public IP**.

> If a shape says "out of capacity", try the other free shape or another region.

---

## Part B — Copy the project to the server

On **your Mac** terminal (replace `KEY.key` with your downloaded key, and `IP`
with the server's public IP):

```bash
chmod 600 ~/Downloads/KEY.key
scp -i ~/Downloads/KEY.key -r ~/ecc-trading ubuntu@IP:~/
```

(This uploads everything, including your `.env` with the Telegram token — so the
token never goes to GitHub.)

---

## Part C — Turn it on

SSH into the server and run the setup script:

```bash
ssh -i ~/Downloads/KEY.key ubuntu@IP
cd ~/ecc-trading
bash deploy/setup_server.sh
```

That's it. The alerter is now running 24/7 and will auto-restart on reboot.
You should get the "🟢 Alerter is live" message on Telegram.

---

## Everyday commands (on the server)

```bash
sudo systemctl status trading-alerts     # is it running?
journalctl -u trading-alerts -f          # live logs
sudo systemctl restart trading-alerts    # restart (e.g. after editing config.py)
sudo systemctl stop trading-alerts       # pause alerts
```

To change settings: edit `config.py` on the server, then `restart`.

---

## Later: upgrade to a paid VPS
When the account grows, a Hetzner/DigitalOcean VPS (~4-6€/mo) is even simpler —
same `setup_server.sh` works there too. Just redo Parts B & C on the new box.
